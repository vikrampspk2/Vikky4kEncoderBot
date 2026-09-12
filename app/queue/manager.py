import asyncio
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Optional

BASE_DIR = Path(__file__).resolve().parents[2]
DB_PATH = BASE_DIR / "config" / "vikky_jobs.db"

DB_PATH.parent.mkdir(parents=True, exist_ok=True)


class PersistentJobManager:
    """
    VIKKY persistent job manager.

    Priority:
      1. Owner jobs
      2. Paid/approved user jobs
      3. Normal user jobs

    Worker policy:
      GPU -> preferred
      CPU -> automatic fallback

    Failure policy:
      retry -> alternate worker -> CPU fallback
    """

    MAX_RETRIES = 5

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = str(db_path)
        self.lock = asyncio.Lock()
        self._init_db()

    def _connect(self):
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        conn = self._connect()

        conn.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                job_id TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                mode TEXT NOT NULL,
                input_file TEXT NOT NULL,
                output_file TEXT,
                priority INTEGER NOT NULL DEFAULT 10,

                status TEXT NOT NULL DEFAULT 'QUEUED',
                worker_id TEXT,
                worker_type TEXT,

                retry_count INTEGER NOT NULL DEFAULT 0,
                max_retries INTEGER NOT NULL DEFAULT 5,

                error TEXT,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                started_at REAL,
                finished_at REAL
            )
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_jobs_status_priority
            ON jobs(status, priority DESC, created_at ASC)
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_jobs_user
            ON jobs(user_id)
        """)

        conn.commit()
        conn.close()

    async def add_job(
        self,
        user_id: int,
        mode: str,
        input_file: str,
        output_file: Optional[str] = None,
        owner: bool = False,
    ) -> str:

        job_id = "VIKKY-" + uuid.uuid4().hex[:12].upper()

        # Owner gets highest priority.
        priority = 100 if owner else 50

        now = time.time()

        async with self.lock:
            conn = self._connect()

            conn.execute("""
                INSERT INTO jobs (
                    job_id,
                    user_id,
                    mode,
                    input_file,
                    output_file,
                    priority,
                    status,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, 'QUEUED', ?, ?)
            """, (
                job_id,
                user_id,
                mode,
                input_file,
                output_file,
                priority,
                now,
                now,
            ))

            conn.commit()
            conn.close()

        return job_id

    async def next_job(self) -> Optional[dict]:
        """
        Get the highest-priority queued job.
        Does not permanently reserve the job until assign_job().
        """

        async with self.lock:
            conn = self._connect()

            row = conn.execute("""
                SELECT *
                FROM jobs
                WHERE status = 'QUEUED'
                ORDER BY priority DESC, created_at ASC
                LIMIT 1
            """).fetchone()

            conn.close()

        return dict(row) if row else None

    async def assign_job(
        self,
        job_id: str,
        worker_id: str,
        worker_type: str,
    ) -> bool:

        async with self.lock:
            conn = self._connect()

            now = time.time()

            cur = conn.execute("""
                UPDATE jobs
                SET
                    status = 'RUNNING',
                    worker_id = ?,
                    worker_type = ?,
                    started_at = COALESCE(started_at, ?),
                    updated_at = ?
                WHERE job_id = ?
                  AND status = 'QUEUED'
            """, (
                worker_id,
                worker_type,
                now,
                now,
                job_id,
            ))

            conn.commit()
            changed = cur.rowcount > 0
            conn.close()

        return changed

    async def mark_success(self, job_id: str):
        async with self.lock:
            conn = self._connect()

            now = time.time()

            conn.execute("""
                UPDATE jobs
                SET
                    status = 'COMPLETED',
                    updated_at = ?,
                    finished_at = ?,
                    error = NULL
                WHERE job_id = ?
            """, (now, now, job_id))

            conn.commit()
            conn.close()

    async def mark_failed(
        self,
        job_id: str,
        error: str,
    ) -> bool:
        """
        Returns:
          True  -> retry available
          False -> retry limit reached
        """

        async with self.lock:
            conn = self._connect()

            row = conn.execute("""
                SELECT retry_count, max_retries
                FROM jobs
                WHERE job_id = ?
            """, (job_id,)).fetchone()

            if not row:
                conn.close()
                return False

            retry_count = int(row["retry_count"])
            max_retries = int(row["max_retries"])

            retry_count += 1
            now = time.time()

            if retry_count <= max_retries:
                conn.execute("""
                    UPDATE jobs
                    SET
                        status = 'QUEUED',
                        worker_id = NULL,
                        worker_type = NULL,
                        retry_count = ?,
                        error = ?,
                        updated_at = ?
                    WHERE job_id = ?
                """, (
                    retry_count,
                    str(error)[:2000],
                    now,
                    job_id,
                ))

                retry_available = True

            else:
                conn.execute("""
                    UPDATE jobs
                    SET
                        status = 'FAILED',
                        retry_count = ?,
                        error = ?,
                        updated_at = ?,
                        finished_at = ?
                    WHERE job_id = ?
                """, (
                    retry_count,
                    str(error)[:2000],
                    now,
                    now,
                    job_id,
                ))

                retry_available = False

            conn.commit()
            conn.close()

        return retry_available

    async def recover_running_jobs(self):
        """
        If VIKKY restarts while a worker was processing,
        move unfinished RUNNING jobs back to QUEUED.
        """

        async with self.lock:
            conn = self._connect()

            now = time.time()

            conn.execute("""
                UPDATE jobs
                SET
                    status = 'QUEUED',
                    worker_id = NULL,
                    worker_type = NULL,
                    updated_at = ?
                WHERE status = 'RUNNING'
            """, (now,))

            conn.commit()
            conn.close()

    async def get_job(self, job_id: str) -> Optional[dict]:
        async with self.lock:
            conn = self._connect()

            row = conn.execute("""
                SELECT *
                FROM jobs
                WHERE job_id = ?
            """, (job_id,)).fetchone()

            conn.close()

        return dict(row) if row else None

    async def pending_count(self) -> int:
        async with self.lock:
            conn = self._connect()

            row = conn.execute("""
                SELECT COUNT(*) AS count
                FROM jobs
                WHERE status = 'QUEUED'
            """).fetchone()

            conn.close()

        return int(row["count"])

    async def running_count(self) -> int:
        async with self.lock:
            conn = self._connect()

            row = conn.execute("""
                SELECT COUNT(*) AS count
                FROM jobs
                WHERE status = 'RUNNING'
            """).fetchone()

            conn.close()

        return int(row["count"])

    async def status(self):
        async with self.lock:
            conn = self._connect()

            rows = conn.execute("""
                SELECT status, COUNT(*) AS count
                FROM jobs
                GROUP BY status
            """).fetchall()

            conn.close()

        return {
            row["status"]: int(row["count"])
            for row in rows
        }


if __name__ == "__main__":
    print("VIKKY PERSISTENT JOB MANAGER READY")
    print("DB:", DB_PATH)

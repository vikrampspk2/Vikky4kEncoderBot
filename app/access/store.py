import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path


DB_PATH = (
    Path(__file__).resolve().parents[2]
    / "config"
    / "vikky_access.db"
)

_lock = threading.RLock()


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


class AccessStore:
    """
    Persistent VIKKY access/permission database.

    Owners are NEVER stored as normal paid users.
    Owner authorization still comes from OWNER_IDS.
    """

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self):
        conn = sqlite3.connect(
            self.db_path,
            timeout=30,
            check_same_thread=False,
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _initialize(self):
        with _lock, self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    status TEXT NOT NULL DEFAULT 'pending',
                    access_until TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS uploaders (
                    user_id INTEGER PRIMARY KEY,
                    added_at TEXT NOT NULL,
                    added_by INTEGER NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1
                );

                CREATE TABLE IF NOT EXISTS access_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    action TEXT NOT NULL,
                    details TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_users_status
                    ON users(status);

                CREATE INDEX IF NOT EXISTS idx_users_access_until
                    ON users(access_until);
                """
            )
            conn.commit()

    def ensure_user(
        self,
        user_id: int,
        username: str | None = None,
        first_name: str | None = None,
    ):
        now = iso(utc_now())

        with _lock, self._connect() as conn:
            existing = conn.execute(
                "SELECT user_id FROM users WHERE user_id = ?",
                (user_id,),
            ).fetchone()

            if existing:
                conn.execute(
                    """
                    UPDATE users
                    SET username = ?,
                        first_name = ?,
                        updated_at = ?
                    WHERE user_id = ?
                    """,
                    (username, first_name, now, user_id),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO users (
                        user_id,
                        username,
                        first_name,
                        status,
                        created_at,
                        updated_at
                    )
                    VALUES (?, ?, ?, 'pending', ?, ?)
                    """,
                    (
                        user_id,
                        username,
                        first_name,
                        now,
                        now,
                    ),
                )

            conn.commit()

    def get_user(self, user_id: int):
        with _lock, self._connect() as conn:
            return conn.execute(
                "SELECT * FROM users WHERE user_id = ?",
                (user_id,),
            ).fetchone()

    def approve_user(self, user_id: int, days: int = 30):
        if days <= 0:
            raise ValueError("days must be greater than zero")

        now = utc_now()
        current = self.get_user(user_id)

        if current and current["access_until"]:
            try:
                current_until = datetime.fromisoformat(
                    current["access_until"]
                )

                if current_until > now:
                    base = current_until
                else:
                    base = now
            except ValueError:
                base = now
        else:
            base = now

        access_until = base + timedelta(days=days)
        now_text = iso(now)
        expiry_text = iso(access_until)

        with _lock, self._connect() as conn:
            conn.execute(
                """
                UPDATE users
                SET status = 'approved',
                    access_until = ?,
                    updated_at = ?
                WHERE user_id = ?
                """,
                (expiry_text, now_text, user_id),
            )

            conn.execute(
                """
                INSERT INTO access_events (
                    user_id,
                    action,
                    details,
                    created_at
                )
                VALUES (?, 'approved', ?, ?)
                """,
                (
                    user_id,
                    f"access_until={expiry_text}",
                    now_text,
                ),
            )

            conn.commit()

        return access_until

    def revoke_user(self, user_id: int):
        now = iso(utc_now())

        with _lock, self._connect() as conn:
            conn.execute(
                """
                UPDATE users
                SET status = 'revoked',
                    access_until = NULL,
                    updated_at = ?
                WHERE user_id = ?
                """,
                (now, user_id),
            )

            conn.execute(
                """
                INSERT INTO access_events (
                    user_id,
                    action,
                    details,
                    created_at
                )
                VALUES (?, 'revoked', NULL, ?)
                """,
                (user_id, now),
            )

            conn.commit()

    def block_user(self, user_id: int):
        now = iso(utc_now())

        with _lock, self._connect() as conn:
            conn.execute(
                """
                UPDATE users
                SET status = 'blocked',
                    updated_at = ?
                WHERE user_id = ?
                """,
                (now, user_id),
            )
            conn.commit()

    def has_active_access(self, user_id: int) -> bool:
        user = self.get_user(user_id)

        if not user:
            return False

        if user["status"] != "approved":
            return False

        if not user["access_until"]:
            return False

        try:
            expiry = datetime.fromisoformat(
                user["access_until"]
            )
        except ValueError:
            return False

        if expiry <= utc_now():
            self._expire_user(user_id)
            return False

        return True

    def _expire_user(self, user_id: int):
        now = iso(utc_now())

        with _lock, self._connect() as conn:
            conn.execute(
                """
                UPDATE users
                SET status = 'expired',
                    updated_at = ?
                WHERE user_id = ?
                AND status = 'approved'
                """,
                (now, user_id),
            )
            conn.commit()

    def add_uploader(
        self,
        user_id: int,
        added_by: int,
    ):
        now = iso(utc_now())

        with _lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO uploaders (
                    user_id,
                    added_at,
                    added_by,
                    enabled
                )
                VALUES (?, ?, ?, 1)
                ON CONFLICT(user_id)
                DO UPDATE SET
                    enabled = 1
                """,
                (user_id, now, added_by),
            )

            conn.commit()

    def remove_uploader(self, user_id: int):
        with _lock, self._connect() as conn:
            conn.execute(
                """
                UPDATE uploaders
                SET enabled = 0
                WHERE user_id = ?
                """,
                (user_id,),
            )
            conn.commit()

    def is_uploader(self, user_id: int) -> bool:
        with _lock, self._connect() as conn:
            row = conn.execute(
                """
                SELECT enabled
                FROM uploaders
                WHERE user_id = ?
                """,
                (user_id,),
            ).fetchone()

        return bool(row and row["enabled"] == 1)

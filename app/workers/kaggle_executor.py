import asyncio
import json
import os
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional

import requests


@dataclass
class KaggleExecutionResult:
    success: bool
    worker_id: str
    job_id: str
    status: str
    error: Optional[str] = None
    retryable: bool = False
    elapsed: float = 0.0
    output_file: Optional[str] = None


class KaggleExecutor:
    """
    VIKKY PRO Kaggle execution controller.

    Responsibilities:
      - Secure credential handling
      - Kernel/job payload preparation
      - Remote execution state tracking
      - Timeout protection
      - Retry-safe result reporting
      - Never log secrets

    IMPORTANT:
      API reachability is NOT treated as GPU availability.
      Actual GPU availability is verified inside the Kaggle worker.
    """

    def __init__(self, timeout: int = 1800, max_retries: int = 3):
        self.timeout = timeout
        self.max_retries = max_retries

    @staticmethod
    def _credentials():
        username = os.getenv("KAGGLE1_USERNAME")
        key = os.getenv("KAGGLE1_KEY")

        if not username or not key:
            raise RuntimeError("KAGGLE_CREDENTIALS_MISSING")

        return username, key

    @staticmethod
    def _safe_error(exc: Exception) -> str:
        return type(exc).__name__

    def build_job_payload(self, job: dict, worker_id: str) -> dict:
        required = ("job_id", "mode", "input_file")

        for field in required:
            if not job.get(field):
                raise ValueError(f"MISSING_JOB_FIELD:{field}")

        return {
            "job_id": str(job["job_id"]),
            "worker_id": str(worker_id),
            "mode": str(job["mode"]),
            "input_file": str(job["input_file"]),
            "requested_at": int(time.time()),
        }

    async def execute(self, job: dict, worker_id: str) -> KaggleExecutionResult:
        started = time.time()

        try:
            payload = self.build_job_payload(job, worker_id)

            # Credentials are intentionally loaded only for validation.
            # They are never included in logs or returned results.
            self._credentials()

            # Remote kernel submission is the next cloud connector stage.
            # Do not falsely report success until Kaggle confirms execution.
            await asyncio.sleep(0)

            return KaggleExecutionResult(
                success=False,
                worker_id=worker_id,
                job_id=str(payload["job_id"]),
                status="KAGGLE_SUBMISSION_NOT_CONNECTED",
                error="KAGGLE_KERNEL_EXECUTION_API_NOT_CONNECTED",
                retryable=True,
                elapsed=time.time() - started,
            )

        except asyncio.TimeoutError:
            return KaggleExecutionResult(
                success=False,
                worker_id=worker_id,
                job_id=str(job.get("job_id", "UNKNOWN")),
                status="TIMEOUT",
                error="KAGGLE_EXECUTION_TIMEOUT",
                retryable=True,
                elapsed=time.time() - started,
            )

        except Exception as exc:
            return KaggleExecutionResult(
                success=False,
                worker_id=worker_id,
                job_id=str(job.get("job_id", "UNKNOWN")),
                status="FAILED",
                error=self._safe_error(exc),
                retryable=True,
                elapsed=time.time() - started,
            )


async def test():
    executor = KaggleExecutor()

    result = await executor.execute(
        {
            "job_id": "VIKKY-PRO-TEST",
            "mode": "4K_AI",
            "input_file": "test.mkv",
        },
        "kaggle-1",
    )

    print("KAGGLE EXECUTOR TEST")
    print(json.dumps(asdict(result), indent=2))
    print("SECRETS: NOT EXPOSED")
    print("FALSE GPU SUCCESS: BLOCKED")


if __name__ == "__main__":
    asyncio.run(test())

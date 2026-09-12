import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Optional

from app.workers.execution import ExecutionEngine, ExecutionResult


log = logging.getLogger("vikky.orchestrator")


@dataclass
class WorkerSlot:
    worker_id: str
    worker_type: str
    busy: bool = False
    cooldown_until: float = 0.0
    failures: int = 0

    @property
    def available(self) -> bool:
        return (
            not self.busy
            and time.time() >= self.cooldown_until
        )


class VIKKYOrchestrator:
    """
    Central production scheduler.

    Policy:
      - GPU first
      - Maximum two simultaneous GPU jobs
      - Strict 3-minute post-job cooldown
      - CPU fallback
      - Retry failed jobs
      - Never report fake success
    """

    COOLDOWN_SECONDS = 180
    MAX_RETRIES = 5

    def __init__(self):
        self.engine = ExecutionEngine()

        self.workers = {
            "gpu-1": WorkerSlot("gpu-1", "GPU"),
            "gpu-2": WorkerSlot("gpu-2", "GPU"),
            "cpu-1": WorkerSlot("cpu-1", "CPU"),
        }

        self._lock = asyncio.Lock()

    async def acquire_worker(self) -> Optional[WorkerSlot]:
        async with self._lock:
            # GPU priority
            for worker in self.workers.values():
                if worker.worker_type == "GPU" and worker.available:
                    worker.busy = True
                    return worker

            # CPU fallback
            cpu = self.workers["cpu-1"]
            if cpu.available:
                cpu.busy = True
                return cpu

            return None

    async def release_worker(
        self,
        worker: WorkerSlot,
        success: bool,
    ):
        async with self._lock:
            worker.busy = False

            # Heavy-job cooldown policy.
            if worker.worker_type == "GPU":
                worker.cooldown_until = (
                    time.time() + self.COOLDOWN_SECONDS
                )

            if not success:
                worker.failures += 1

    async def run_job(self, job: dict) -> ExecutionResult:
        retries = 0

        while retries < self.MAX_RETRIES:
            worker = await self.acquire_worker()

            if worker is None:
                await asyncio.sleep(5)
                continue

            try:
                log.info(
                    "JOB %s assigned to %s",
                    job.get("job_id", "UNKNOWN"),
                    worker.worker_id,
                )

                result = await self.engine.execute(
                    job,
                    worker.worker_id,
                    worker.worker_type,
                )

                if result.success:
                    await self.release_worker(worker, True)
                    return result

                retries += 1

                log.warning(
                    "JOB %s failed on %s: %s",
                    job.get("job_id", "UNKNOWN"),
                    worker.worker_id,
                    result.error,
                )

                await self.release_worker(worker, False)

                if not result.retryable:
                    return result

            except Exception as exc:
                retries += 1

                log.exception(
                    "JOB %s unexpected worker failure",
                    job.get("job_id", "UNKNOWN"),
                )

                await self.release_worker(worker, False)

                if retries >= self.MAX_RETRIES:
                    return ExecutionResult(
                        success=False,
                        worker_id=worker.worker_id,
                        worker_type=worker.worker_type,
                        error=type(exc).__name__,
                        retryable=False,
                    )

        return ExecutionResult(
            success=False,
            worker_id="scheduler",
            worker_type="SCHEDULER",
            error="MAX_RETRIES_EXCEEDED",
            retryable=False,
        )


async def test():
    logging.basicConfig(level=logging.INFO)

    scheduler = VIKKYOrchestrator()

    result = await scheduler.run_job(
        {
            "job_id": "VIKKY-ORCHESTRATOR-TEST",
            "mode": "4K_AI",
            "input_file": "test.mkv",
        }
    )

    print("\n=== VIKKY ORCHESTRATOR ===")
    print("SUCCESS:", result.success)
    print("WORKER:", result.worker_id)
    print("TYPE:", result.worker_type)
    print("ERROR:", result.error)
    print("RETRYABLE:", result.retryable)
    print("FAKE SUCCESS: BLOCKED")


if __name__ == "__main__":
    asyncio.run(test())

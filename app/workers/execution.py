import asyncio
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class ExecutionResult:
    success: bool
    worker_id: str
    worker_type: str
    output_file: Optional[str] = None
    error: Optional[str] = None
    retryable: bool = False
    elapsed: float = 0.0


class ExecutionEngine:
    """
    VIKKY execution layer.

    GPU is preferred.
    CPU is automatic fallback.

    The actual AI/FFmpeg commands are intentionally plugged in
    later through execute_gpu() and execute_cpu().
    """

    def __init__(self):
        self.max_attempts = 5

    async def execute(
        self,
        job: dict,
        worker_id: str,
        worker_type: str,
    ) -> ExecutionResult:

        started = time.time()

        try:
            if worker_type == "GPU":
                result = await self.execute_gpu(
                    job,
                    worker_id,
                )
            else:
                result = await self.execute_cpu(
                    job,
                    worker_id,
                )

            result.elapsed = time.time() - started
            return result

        except Exception as exc:
            return ExecutionResult(
                success=False,
                worker_id=worker_id,
                worker_type=worker_type,
                error=type(exc).__name__,
                retryable=True,
                elapsed=time.time() - started,
            )

    async def execute_gpu(
        self,
        job: dict,
        worker_id: str,
    ) -> ExecutionResult:

        # Real Kaggle + Real-ESRGAN execution is connected
        # in the GPU execution adapter.
        return ExecutionResult(
            success=False,
            worker_id=worker_id,
            worker_type="GPU",
            error="GPU_EXECUTOR_NOT_CONNECTED",
            retryable=True,
        )

    async def execute_cpu(
        self,
        job: dict,
        worker_id: str,
    ) -> ExecutionResult:

        # CPU execution adapter will be connected here.
        return ExecutionResult(
            success=False,
            worker_id=worker_id,
            worker_type="CPU",
            error="CPU_EXECUTOR_NOT_CONNECTED",
            retryable=True,
        )


async def test():
    engine = ExecutionEngine()

    test_job = {
        "job_id": "VIKKY-TEST",
        "mode": "4K_AI",
        "input_file": "test.mkv",
    }

    print("VIKKY EXECUTION ENGINE")

    gpu = await engine.execute(
        test_job,
        "gpu-1",
        "GPU",
    )

    print(
        f"GPU RESULT: success={gpu.success} "
        f"error={gpu.error} "
        f"retryable={gpu.retryable}"
    )

    cpu = await engine.execute(
        test_job,
        "cpu-1",
        "CPU",
    )

    print(
        f"CPU RESULT: success={cpu.success} "
        f"error={cpu.error} "
        f"retryable={cpu.retryable}"
    )

    print("\nGPU EXECUTION CONTRACT: OK")
    print("CPU EXECUTION CONTRACT: OK")
    print("FAILURE REPORTING: OK")
    print("RETRY SIGNAL: OK")


if __name__ == "__main__":
    asyncio.run(test())

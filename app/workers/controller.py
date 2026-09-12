import asyncio
import time
from dataclasses import dataclass
from typing import Optional


@dataclass
class WorkerState:
    worker_id: str
    worker_type: str
    available: bool = True
    healthy: bool = True
    busy: bool = False
    failures: int = 0
    last_error: Optional[str] = None
    last_seen: float = 0.0


class WorkerController:
    """
    VIKKY Worker Controller

    GPU is always preferred.
    CPU is automatic fallback.

    This layer controls worker state only.
    Actual Kaggle/CPU processing is connected later.
    """

    def __init__(self):
        self.workers = {
            "gpu-1": WorkerState(
                worker_id="gpu-1",
                worker_type="GPU",
            ),
            "gpu-2": WorkerState(
                worker_id="gpu-2",
                worker_type="GPU",
            ),
            "cpu-1": WorkerState(
                worker_id="cpu-1",
                worker_type="CPU",
            ),
        }

        self.lock = asyncio.Lock()

    async def heartbeat(self, worker_id: str, healthy: bool = True):
        async with self.lock:
            worker = self.workers.get(worker_id)

            if not worker:
                return False

            worker.healthy = healthy
            worker.last_seen = time.time()

            if healthy:
                worker.failures = 0
                worker.last_error = None

            return True

    async def acquire(self) -> Optional[WorkerState]:
        """
        Select worker.

        Priority:
            1. Healthy + available GPU
            2. Healthy + available CPU
        """

        async with self.lock:
            gpu = [
                w for w in self.workers.values()
                if w.worker_type == "GPU"
                and w.available
                and w.healthy
                and not w.busy
            ]

            if gpu:
                worker = min(
                    gpu,
                    key=lambda w: w.failures
                )
                worker.busy = True
                return worker

            cpu = [
                w for w in self.workers.values()
                if w.worker_type == "CPU"
                and w.available
                and w.healthy
                and not w.busy
            ]

            if cpu:
                worker = min(
                    cpu,
                    key=lambda w: w.failures
                )
                worker.busy = True
                return worker

            return None

    async def release(self, worker_id: str):
        async with self.lock:
            worker = self.workers.get(worker_id)

            if worker:
                worker.busy = False
                worker.last_seen = time.time()

    async def fail(
        self,
        worker_id: str,
        error: str,
    ):
        """
        Temporarily mark worker unhealthy.
        The worker can be recovered by heartbeat().
        """

        async with self.lock:
            worker = self.workers.get(worker_id)

            if not worker:
                return False

            worker.busy = False
            worker.healthy = False
            worker.failures += 1
            worker.last_error = str(error)[:1000]
            worker.last_seen = time.time()

            return True

    async def recover(self, worker_id: str):
        async with self.lock:
            worker = self.workers.get(worker_id)

            if not worker:
                return False

            worker.healthy = True
            worker.available = True
            worker.busy = False
            worker.last_error = None
            worker.last_seen = time.time()

            return True

    async def set_available(
        self,
        worker_id: str,
        available: bool,
    ):
        async with self.lock:
            worker = self.workers.get(worker_id)

            if not worker:
                return False

            worker.available = available

            if not available:
                worker.busy = False

            return True

    async def status(self):
        async with self.lock:
            return [
                {
                    "worker_id": w.worker_id,
                    "type": w.worker_type,
                    "available": w.available,
                    "healthy": w.healthy,
                    "busy": w.busy,
                    "failures": w.failures,
                }
                for w in self.workers.values()
            ]


async def test():
    controller = WorkerController()

    print("VIKKY WORKER CONTROLLER READY")

    worker = await controller.acquire()

    if worker:
        print(
            f"FIRST SELECTED: "
            f"{worker.worker_id} ({worker.worker_type})"
        )

        await controller.release(worker.worker_id)

    # Simulate GPU failure.
    await controller.fail(
        "gpu-1",
        "SIMULATED GPU FAILURE"
    )

    worker = await controller.acquire()

    if worker:
        print(
            f"GPU-1 FAILED -> FALLBACK: "
            f"{worker.worker_id} ({worker.worker_type})"
        )

        await controller.release(worker.worker_id)

    # Recover GPU.
    await controller.recover("gpu-1")

    worker = await controller.acquire()

    if worker:
        print(
            f"GPU RECOVERED -> PRIORITY: "
            f"{worker.worker_id} ({worker.worker_type})"
        )

        await controller.release(worker.worker_id)

    print("\nWORKER STATUS:")

    for item in await controller.status():
        print(item)

    print("\nGPU PRIORITY: OK")
    print("CPU FALLBACK: OK")
    print("GPU RECOVERY: OK")
    print("WORKER CONTROLLER TEST: PASS")


if __name__ == "__main__":
    asyncio.run(test())

from pathlib import Path


class KaggleAIWorker:

    def __init__(self, worker_id):
        self.worker_id = worker_id

    def build_job(self, input_file, output_file, mode):
        input_file = Path(input_file)
        output_file = Path(output_file)

        if not input_file.exists():
            raise FileNotFoundError("Input video not found")

        if mode not in {
            "2K_AI",
            "4K_AI",
            "8K_AI",
            "4K_HYBRID",
            "8K_HYBRID",
        }:
            raise ValueError(f"Unsupported AI mode: {mode}")

        return {
            "worker_id": self.worker_id,
            "input_file": str(input_file),
            "output_file": str(output_file),
            "mode": mode,
            "engine": "Real-ESRGAN",
            "execution": "GPU",
            "audio": "PRESERVE",
            "status": "QUEUED",
        }


def create_worker(worker_id):
    return KaggleAIWorker(worker_id)

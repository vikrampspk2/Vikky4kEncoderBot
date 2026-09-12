import os
import sys
import subprocess
from pathlib import Path


def run(command):
    print("[VIKKY]", " ".join(map(str, command)), flush=True)
    result = subprocess.run(command, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Command failed: {result.returncode}")
    return result


def check_gpu():
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total,driver_version",
                "--format=csv,noheader",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            return False, result.stderr.strip()

        print("GPU:", result.stdout.strip(), flush=True)
        return True, result.stdout.strip()
    except Exception as exc:
        return False, type(exc).__name__


def check_torch():
    try:
        import torch

        print("TORCH:", torch.__version__, flush=True)
        print("CUDA AVAILABLE:", torch.cuda.is_available(), flush=True)

        if not torch.cuda.is_available():
            return False

        print("CUDA DEVICE:", torch.cuda.get_device_name(0), flush=True)
        print("CUDA VERSION:", torch.version.cuda, flush=True)

        return True
    except Exception as exc:
        print("TORCH ERROR:", type(exc).__name__, str(exc), flush=True)
        return False


def main():
    print("=== VIKKY REAL GPU WORKER ===", flush=True)

    gpu_ok, gpu_info = check_gpu()
    if not gpu_ok:
        raise RuntimeError(f"GPU_UNAVAILABLE: {gpu_info}")

    torch_ok = check_torch()
    if not torch_ok:
        raise RuntimeError("CUDA_PYTORCH_UNAVAILABLE")

    print("GPU WORKER: READY", flush=True)
    print("AI ENGINE: Real-ESRGAN", flush=True)
    print("STATUS: GPU_RUNTIME_VERIFIED", flush=True)


if __name__ == "__main__":
    main()

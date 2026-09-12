import subprocess
import sys

print("=== VIKKY CLOUD GPU SMOKE TEST ===")

try:
    r = subprocess.run(
        ["nvidia-smi", "--query-gpu=name,memory.total,driver_version",
         "--format=csv,noheader"],
        capture_output=True,
        text=True,
        timeout=30
    )
    print("NVIDIA-SMI RETURN:", r.returncode)
    print(r.stdout.strip() or r.stderr.strip())
except Exception as e:
    print("NVIDIA-SMI ERROR:", type(e).__name__, str(e))

try:
    import torch
    print("TORCH:", torch.__version__)
    print("CUDA AVAILABLE:", torch.cuda.is_available())
    if torch.cuda.is_available():
        print("CUDA DEVICE:", torch.cuda.get_device_name(0))
        print("CUDA VERSION:", torch.version.cuda)
except Exception as e:
    print("PYTORCH CHECK:", type(e).__name__, str(e))

print("=== TEST COMPLETE ===")

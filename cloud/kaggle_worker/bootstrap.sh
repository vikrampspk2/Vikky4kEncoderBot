#!/usr/bin/env bash
set -euo pipefail

echo "=== VIKKY CLOUD BOOTSTRAP ==="

python3 --version
python3 -m pip --version

python3 -m pip install --upgrade pip
python3 -m pip install kaggle

echo "=== KAGGLE CLI ==="
kaggle --version

echo "=== GPU ==="
nvidia-smi

echo "=== PYTORCH ==="
python3 - <<'PY'
import torch

print("TORCH:", torch.__version__)
print("CUDA:", torch.cuda.is_available())

if not torch.cuda.is_available():
    raise SystemExit("CUDA_UNAVAILABLE")

print("GPU:", torch.cuda.get_device_name(0))
print("CUDA VERSION:", torch.version.cuda)
PY

echo "=== AI PACKAGES ==="
python3 - <<'PY'
import cv2
import numpy
from PIL import Image

print("OpenCV:", cv2.__version__)
print("NumPy:", numpy.__version__)
print("Pillow: OK")
PY

echo "=== VIKKY GPU ENVIRONMENT: VERIFIED ==="

import subprocess
import sys

def prep_env():
    pkgs = ["basicsr", "facexlib", "gfpgan", "realesrgan", "ffmpeg-python"]
    for p in pkgs:
        try:
            __import__(p)
        except ImportError:
            subprocess.run([sys.executable, "-m", "pip", "install", "--no-cache-dir", p], check=False)

prep_env()

import os
import json
import time
import shutil
import hashlib
from pathlib import Path

import cv2
import numpy as np
import torch
import urllib.request

from basicsr.archs.rrdbnet_arch import RRDBNet
from realesrgan import RealESRGANer

APP = "VIKKY AI GPU WORKER"
MODEL_NAME = "RealESRGAN_x4plus"

INPUT_ROOT = Path("/kaggle/input")
WORK_ROOT = Path("/kaggle/working/vikky")
WEIGHTS_DIR = WORK_ROOT / "weights"
OUTPUT_DIR = WORK_ROOT / "output"

WORK_ROOT.mkdir(parents=True, exist_ok=True)
WEIGHTS_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

MODEL_URL = "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.1.0/RealESRGAN_x4plus.pth"
MODEL_PATH = WEIGHTS_DIR / "RealESRGAN_x4plus.pth"

def log(msg):
    print(f"[VIKKY] {msg}", flush=True)

def fail(msg):
    print(f"[VIKKY][ERROR] {msg}", flush=True)
    sys.exit(1)

def check_gpu():
    if not torch.cuda.is_available():
        fail("PyTorch CUDA is NOT available")
    name = torch.cuda.get_device_name(0)
    log(f"Using GPU: {name}")
    return name

def find_input_video():
    exts = {".mp4", ".mkv", ".mov", ".avi", ".webm"}
    videos = [p for p in INPUT_ROOT.rglob("*") if p.is_file() and p.suffix.lower() in exts]
    if not videos:
        fail("No video found under /kaggle/input")
    videos.sort(key=lambda p: p.stat().st_size, reverse=True)
    log(f"Found input: {videos[0]}")
    return videos[0]

def download_model():
    if MODEL_PATH.exists() and MODEL_PATH.stat().st_size > 10_000_000:
        return
    log("Downloading RealESRGAN model...")
    urllib.request.urlretrieve(MODEL_URL, str(MODEL_PATH))

def target_resolution(w, h):
    target_long = 3840
    src_long = max(w, h)
    scale = target_long / src_long
    out_w = max(2, int(round(w * scale)))
    out_h = max(2, int(round(h * scale)))
    out_w -= out_w % 2
    out_h -= out_h % 2
    return out_w, out_h

def main():
    gpu = check_gpu()
    source = find_input_video()
    download_model()

    cap = cv2.VideoCapture(str(source))
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    out_w, out_h = target_resolution(w, h)
    log(f"Processing {w}x{h} -> {out_w}x{out_h} at {fps:.2f} fps ({total} frames)")

    model = RRDBNet(num_in_ch=3, num_out_ch=3, num_feat=64, num_block=23, num_grow_ch=32, scale=4)
    upsampler = RealESRGANer(scale=4, model_path=str(MODEL_PATH), model=model, tile=256, tile_pad=10, pre_pad=0, half=True, device=torch.device("cuda"))

    output = OUTPUT_DIR / f"{source.stem}.4K.Upscaled.By.VIKKY.mkv"
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "rawvideo", "-pix_fmt", "bgr24", "-s:v", f"{out_w}x{out_h}", "-r", f"{fps:.06f}", "-i", "pipe:0",
        "-i", str(source), "-map", "0:v:0", "-map", "1:a?", "-map", "1:s?",
        "-c:v", "libx265", "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p10le",
        "-c:a", "copy", "-c:s", "copy", "-map_metadata", "1", "-f", "matroska", str(output)
    ]
    ffmpeg = subprocess.Popen(cmd, stdin=subprocess.PIPE)

    count = 0
    t0 = time.time()
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        enhanced, _ = upsampler.enhance(frame, outscale=4)
        if enhanced.shape[1] != out_w or enhanced.shape[0] != out_h:
            enhanced = cv2.resize(enhanced, (out_w, out_h), interpolation=cv2.INTER_LANCZOS4)
        ffmpeg.stdin.write(np.ascontiguousarray(enhanced, dtype=np.uint8).tobytes())
        count += 1
        if count % 20 == 0:
            log(f"Upscaled {count}/{total} frames ({(count/total)*100:.1f}%)")

    cap.release()
    ffmpeg.stdin.close()
    ffmpeg.wait()

    elapsed = time.time() - t0
    log(f"FINISHED! Rendered {count} frames in {elapsed:.1f}s -> {output}")

if __name__ == "__main__":
    main()

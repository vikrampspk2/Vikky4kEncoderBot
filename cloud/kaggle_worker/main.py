import os
import sys
import json
import time
import shutil
import hashlib
import subprocess
import urllib.request
from pathlib import Path

import cv2
import numpy as np
import torch

from basicsr.archs.rrdbnet_arch import RRDBNet
from realesrgan import RealESRGANer


# ============================================================
# VIKKY AI GPU WORKER
# Real-ESRGAN x4plus video processing
# ============================================================

APP = "VIKKY AI GPU WORKER"
MODEL_NAME = "RealESRGAN_x4plus"

INPUT_ROOT = Path("/kaggle/input")
WORK_ROOT = Path("/kaggle/working/vikky")
WEIGHTS_DIR = WORK_ROOT / "weights"
OUTPUT_DIR = WORK_ROOT / "output"

WORK_ROOT.mkdir(parents=True, exist_ok=True)
WEIGHTS_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

MODEL_URL = (
    "https://github.com/xinntao/Real-ESRGAN/"
    "releases/download/v0.1.0/RealESRGAN_x4plus.pth"
)

MODEL_PATH = WEIGHTS_DIR / "RealESRGAN_x4plus.pth"


# ============================================================
# LOGGING
# ============================================================

def log(msg):
    print(f"[VIKKY] {msg}", flush=True)


def fail(msg):
    print(f"[VIKKY][ERROR] {msg}", flush=True)
    sys.exit(1)


# ============================================================
# COMMAND CHECK
# ============================================================

def command_exists(name):
    return shutil.which(name) is not None


# ============================================================
# GPU CHECK
# ============================================================

def check_gpu():
    log("Checking NVIDIA GPU...")

    if not command_exists("nvidia-smi"):
        fail("nvidia-smi not found")

    result = subprocess.run(
        [
            "nvidia-smi",
            "--query-gpu=name,memory.total,driver_version",
            "--format=csv,noheader",
        ],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        fail("NVIDIA GPU is not available")

    log(f"GPU: {result.stdout.strip()}")

    if not torch.cuda.is_available():
        fail("PyTorch CUDA is NOT available")

    device_name = torch.cuda.get_device_name(0)
    cuda_version = torch.version.cuda

    log(f"CUDA: {cuda_version}")
    log(f"PyTorch GPU: {device_name}")

    torch.cuda.empty_cache()

    return device_name


# ============================================================
# FIND INPUT VIDEO
# ============================================================

VIDEO_EXTENSIONS = {
    ".mp4",
    ".mkv",
    ".mov",
    ".avi",
    ".webm",
    ".m4v",
    ".ts",
    ".mts",
}


def find_input_video():
    log("Searching /kaggle/input for video...")

    videos = []

    for path in INPUT_ROOT.rglob("*"):
        if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS:
            videos.append(path)

    if not videos:
        fail("No input video found under /kaggle/input")

    videos.sort(key=lambda p: p.stat().st_size, reverse=True)

    source = videos[0]

    log(f"Input: {source}")
    log(
        f"Input size: "
        f"{source.stat().st_size / (1024 * 1024):.2f} MB"
    )

    return source


# ============================================================
# DOWNLOAD MODEL
# ============================================================

def download_model():
    if MODEL_PATH.exists() and MODEL_PATH.stat().st_size > 10_000_000:
        log("Real-ESRGAN model already exists")
        return

    log("Downloading Real-ESRGAN x4plus model...")
    log(MODEL_URL)

    temp_path = MODEL_PATH.with_suffix(".download")

    try:
        urllib.request.urlretrieve(MODEL_URL, temp_path)
    except Exception as exc:
        if temp_path.exists():
            temp_path.unlink()
        fail(f"Model download failed: {exc}")

    if not temp_path.exists():
        fail("Model download produced no file")

    if temp_path.stat().st_size < 10_000_000:
        temp_path.unlink()
        fail("Downloaded model file is invalid")

    temp_path.replace(MODEL_PATH)

    log(
        f"Model downloaded: "
        f"{MODEL_PATH.stat().st_size / (1024 * 1024):.2f} MB"
    )


# ============================================================
# VIDEO INFO
# ============================================================

def get_video_info(source):
    cap = cv2.VideoCapture(str(source))

    if not cap.isOpened():
        fail("OpenCV cannot open input video")

    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    cap.release()

    if width <= 0 or height <= 0:
        fail("Invalid input resolution")

    if fps <= 0:
        fps = 30.0

    duration = frames / fps if frames > 0 else 0

    info = {
        "width": width,
        "height": height,
        "fps": fps,
        "frames": frames,
        "duration": duration,
    }

    log(
        f"Source: {width}x{height} | "
        f"{fps:.3f} FPS | "
        f"{frames} frames | "
        f"{duration:.2f}s"
    )

    return info


# ============================================================
# TARGET RESOLUTION
# ============================================================

def target_resolution(width, height):
    """
    Target = 4K long edge.

    Portrait:
        360x640 -> 2160x3840

    Landscape:
        640x360 -> 3840x2160
    """

    target_long_edge = 3840

    source_long_edge = max(width, height)

    scale = target_long_edge / source_long_edge

    out_w = max(2, int(round(width * scale)))
    out_h = max(2, int(round(height * scale)))

    # Even dimensions for video encoders.
    out_w -= out_w % 2
    out_h -= out_h % 2

    return out_w, out_h


# ============================================================
# REAL-ESRGAN MODEL
# ============================================================

def create_upsampler():
    log("Building Real-ESRGAN x4plus model...")

    model = RRDBNet(
        num_in_ch=3,
        num_out_ch=3,
        num_feat=64,
        num_block=23,
        num_grow_ch=32,
        scale=4,
    )

    upsampler = RealESRGANer(
        scale=4,
        model_path=str(MODEL_PATH),
        model=model,
        tile=256,
        tile_pad=10,
        pre_pad=0,
        half=True,
        device=torch.device("cuda"),
    )

    log("Real-ESRGAN GPU model READY")

    return upsampler


# ============================================================
# FFMPEG ENCODER
# ============================================================

def start_ffmpeg(
    source,
    output,
    width,
    height,
    fps,
):
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",

        # AI frames
        "-f",
        "rawvideo",
        "-pix_fmt",
        "bgr24",
        "-s:v",
        f"{width}x{height}",
        "-r",
        f"{fps:.06f}",
        "-i",
        "pipe:0",

        # Original source for audio/subtitles
        "-i",
        str(source),

        # Video from AI
        "-map",
        "0:v:0",

        # Original audio/subtitles
        "-map",
        "1:a?",
        "-map",
        "1:s?",

        # High quality HEVC
        "-c:v",
        "libx265",
        "-preset",
        "medium",
        "-crf",
        "18",

        # 10-bit output
        "-pix_fmt",
        "yuv420p10le",

        # Preserve audio/subtitles
        "-c:a",
        "copy",
        "-c:s",
        "copy",

        # Preserve metadata
        "-map_metadata",
        "1",

        # MKV
        "-f",
        "matroska",
        str(output),
    ]

    log("Starting FFmpeg HEVC encoder...")

    return subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )


# ============================================================
# SHA256
# ============================================================

def sha256_file(path):
    h = hashlib.sha256()

    with open(path, "rb") as f:
        while True:
            chunk = f.read(1024 * 1024)

            if not chunk:
                break

            h.update(chunk)

    return h.hexdigest()


# ============================================================
# OUTPUT VALIDATION
# ============================================================

def validate_output(output):
    if not output.exists():
        fail("Output file was not created")

    size = output.stat().st_size

    if size < 1024:
        fail("Output file is suspiciously small")

    log(
        f"Output size: "
        f"{size / (1024 * 1024):.2f} MB"
    )

    probe = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=codec_name,width,height,pix_fmt",
            "-of",
            "json",
            str(output),
        ],
        capture_output=True,
        text=True,
    )

    if probe.returncode != 0:
        fail("FFprobe validation failed")

    try:
        data = json.loads(probe.stdout)
    except Exception:
        fail("Invalid FFprobe JSON")

    streams = data.get("streams", [])

    if not streams:
        fail("No video stream in output")

    video = streams[0]

    log(
        f"Output video: "
        f"{video.get('codec_name')} "
        f"{video.get('width')}x{video.get('height')} "
        f"{video.get('pix_fmt')}"
    )

    return video


# ============================================================
# MAIN PROCESS
# ============================================================

def main():

    start_time = time.time()

    print()
    print("=" * 64)
    print(" VIKKY AI GPU WORKER")
    print(" REAL-ESRGAN x4plus VIDEO UPSCALE")
    print("=" * 64)
    print()

    # GPU
    gpu_name = check_gpu()

    # Input
    source = find_input_video()

    # Video information
    info = get_video_info(source)

    source_w = info["width"]
    source_h = info["height"]
    fps = info["fps"]
    total_frames = info["frames"]

    # Target
    target_w, target_h = target_resolution(
        source_w,
        source_h,
    )

    log(
        f"AI target: "
        f"{target_w}x{target_h}"
    )

    # Model
    download_model()

    upsampler = create_upsampler()

    # Output
    stem = source.stem

    output = OUTPUT_DIR / (
        f"{stem}.4K.Upscaled.By.VIKKY.mkv"
    )

    # Encoder
    ffmpeg = start_ffmpeg(
        source,
        output,
        target_w,
        target_h,
        fps,
    )

    cap = cv2.VideoCapture(str(source))

    if not cap.isOpened():
        ffmpeg.kill()
        fail("Cannot reopen input video")

    processed = 0
    failed_frames = 0

    last_report = time.time()

    try:

        while True:

            ok, frame = cap.read()

            if not ok:
                break

            try:

                # Actual AI inference
                output_frame, _ = upsampler.enhance(
                    frame,
                    outscale=4,
                )

                # Real-ESRGAN x4 output can be slightly different
                # from exact target. Resize only to target dimensions.
                if (
                    output_frame.shape[1] != target_w
                    or output_frame.shape[0] != target_h
                ):
                    output_frame = cv2.resize(
                        output_frame,
                        (target_w, target_h),
                        interpolation=cv2.INTER_LANCZOS4,
                    )

                # Send AI frame directly to FFmpeg.
                ffmpeg.stdin.write(
                    np.ascontiguousarray(
                        output_frame,
                        dtype=np.uint8,
                    ).tobytes()
                )

                processed += 1

            except Exception as exc:

                failed_frames += 1

                log(
                    f"Frame {processed + 1} failed: "
                    f"{type(exc).__name__}: {exc}"
                )

                raise

            # Progress
            now = time.time()

            if now - last_report >= 5:

                elapsed = now - start_time

                if elapsed > 0:
                    speed = processed / elapsed
                else:
                    speed = 0

                if total_frames > 0:
                    percent = (
                        processed /
                        total_frames *
                        100
                    )
                else:
                    percent = 0

                log(
                    f"Progress: "
                    f"{processed}/{total_frames} "
                    f"({percent:.1f}%) | "
                    f"{speed:.2f} FPS"
                )

                last_report = now

    except BrokenPipeError:
        raise RuntimeError(
            "FFmpeg pipe closed unexpectedly"
        )

    finally:
        cap.release()

        try:
            ffmpeg.stdin.close()
        except Exception:
            pass

    stderr = ffmpeg.stderr.read().decode(
        "utf-8",
        errors="replace",
    )

    return_code = ffmpeg.wait()

    if return_code != 0:

        log("FFmpeg ERROR:")
        print(stderr)

        fail(
            f"FFmpeg exited with code "
            f"{return_code}"
        )

    # Validation
    video_stream = validate_output(output)

    # Hash
    log("Calculating SHA256...")

    sha256 = sha256_file(output)

    elapsed = time.time() - start_time

    # Report
    report = {
        "project": "VIKKY Encoder",
        "worker": APP,
        "status": "GPU_AI_INFERENCE_COMPLETE",
        "engine": MODEL_NAME,
        "gpu": gpu_name,
        "cuda": torch.version.cuda,
        "source": {
            "width": source_w,
            "height": source_h,
            "fps": fps,
            "frames": total_frames,
            "duration_seconds": info["duration"],
        },
        "output": {
            "width": video_stream.get("width"),
            "height": video_stream.get("height"),
            "codec": video_stream.get("codec_name"),
            "pixel_format": video_stream.get("pix_fmt"),
            "path": str(output),
            "size_bytes": output.stat().st_size,
            "sha256": sha256,
        },
        "processing": {
            "frames_processed": processed,
            "failed_frames": failed_frames,
            "elapsed_seconds": elapsed,
            "temporal_consistency": "not_applied",
            "face_enhancement": "not_applied",
            "audio": "source_tracks_copied",
            "subtitles": "source_tracks_copied",
        },
    }

    report_path = OUTPUT_DIR / "vikky_ai_report.json"

    with open(
        report_path,
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            report,
            f,
            indent=2,
        )

    print()
    print("=" * 64)
    print(" VIKKY AI PROCESSING COMPLETE")
    print("=" * 64)
    print(f"GPU       : {gpu_name}")
    print(f"ENGINE    : {MODEL_NAME}")
    print(f"INPUT     : {source_w}x{source_h}")
    print(f"OUTPUT    : {video_stream.get('width')}x{video_stream.get('height')}")
    print(f"FRAMES    : {processed}")
    print(f"OUTPUT    : {output}")
    print(f"SHA256    : {sha256}")
    print(f"TIME      : {elapsed:.2f}s")
    print(f"REPORT    : {report_path}")
    print("=" * 64)
    print()


if __name__ == "__main__":
    main()

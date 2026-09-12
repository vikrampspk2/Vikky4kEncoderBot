import asyncio
import json
import os
import shutil
import time
from pathlib import Path
from typing import Optional


VIDEO_ENCODERS = {
    "h264_nvenc": "GPU",
    "hevc_nvenc": "GPU",
    "libx265": "CPU",
}


class FFmpegExecutor:
    """
    VIKKY real FFmpeg execution layer.

    Policy:
      - Prefer hardware HEVC when available.
      - Otherwise use CPU x265.
      - Audio/subtitles are copied whenever compatible.
      - Failed/partial outputs are removed.
      - Never reports success unless the output is valid.
    """

    def __init__(self):
        self.ffmpeg = shutil.which("ffmpeg")
        self.ffprobe = shutil.which("ffprobe")

    async def _run(self, command: list[str]) -> tuple[int, str]:
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await process.communicate()

        text = (
            stdout.decode(errors="replace")
            + "\n"
            + stderr.decode(errors="replace")
        )

        return process.returncode, text

    async def gpu_encoder_available(self) -> bool:
        """
        Check whether NVENC encoders are actually exposed by FFmpeg.
        """

        if not self.ffmpeg:
            return False

        code, output = await self._run([
            self.ffmpeg,
            "-hide_banner",
            "-encoders",
        ])

        if code != 0:
            return False

        return (
            "hevc_nvenc" in output
            or "h264_nvenc" in output
        )

    async def probe(self, input_file: str) -> Optional[dict]:
        if not self.ffprobe:
            return None

        command = [
            self.ffprobe,
            "-v", "error",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            input_file,
        ]

        code, output = await self._run(command)

        if code != 0:
            return None

        try:
            return json.loads(output)
        except json.JSONDecodeError:
            return None

    async def validate_output(self, output_file: str) -> bool:
        if not os.path.isfile(output_file):
            return False

        if os.path.getsize(output_file) < 1024:
            return False

        info = await self.probe(output_file)

        if not info:
            return False

        streams = info.get("streams", [])

        return any(
            stream.get("codec_type") == "video"
            for stream in streams
        )

    async def encode(
        self,
        input_file: str,
        output_file: str,
        prefer_gpu: bool = True,
    ) -> dict:

        started = time.time()

        if not self.ffmpeg:
            return {
                "success": False,
                "error": "FFMPEG_NOT_FOUND",
            }

        if not os.path.isfile(input_file):
            return {
                "success": False,
                "error": "INPUT_NOT_FOUND",
            }

        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        if output_path.exists():
            output_path.unlink()

        use_gpu = False

        if prefer_gpu:
            use_gpu = await self.gpu_encoder_available()

        if use_gpu:
            encoder = "hevc_nvenc"
            encoder_type = "GPU"

            video_options = [
                "-c:v", encoder,
                "-preset", "p5",
                "-cq", "20",
                "-profile:v", "main",
            ]

        else:
            encoder = "libx265"
            encoder_type = "CPU"

            video_options = [
                "-c:v", encoder,
                "-preset", "medium",
                "-crf", "20",
                "-pix_fmt", "yuv420p10le",
            ]

        command = [
            self.ffmpeg,
            "-hide_banner",
            "-y",
            "-i", input_file,

            *video_options,

            # Preserve all audio/subtitle streams where possible.
            "-map", "0:v:0",
            "-map", "0:a?",
            "-map", "0:s?",

            "-c:a", "copy",
            "-c:s", "copy",

            "-max_muxing_queue_size", "4096",

            output_file,
        ]

        code, log = await self._run(command)

        if code == 0:
            valid = await self.validate_output(output_file)

            if valid:
                return {
                    "success": True,
                    "worker_type": encoder_type,
                    "encoder": encoder,
                    "output_file": output_file,
                    "elapsed": round(time.time() - started, 2),
                }

        # Remove corrupt/partial output.
        if output_path.exists():
            try:
                output_path.unlink()
            except OSError:
                pass

        return {
            "success": False,
            "worker_type": encoder_type,
            "encoder": encoder,
            "error": "ENCODE_FAILED",
            "log_tail": log[-2000:],
            "elapsed": round(time.time() - started, 2),
        }


async def main():
    executor = FFmpegExecutor()

    print("VIKKY REAL FFMPEG EXECUTOR")

    if executor.ffmpeg:
        print("FFMPEG: FOUND")
    else:
        print("FFMPEG: NOT FOUND")

    if executor.ffprobe:
        print("FFPROBE: FOUND")
    else:
        print("FFPROBE: NOT FOUND")

    gpu = await executor.gpu_encoder_available()

    print("NVENC AVAILABLE:", gpu)

    print("\nFFMPEG EXECUTOR: READY")
    print("GPU PREFERENCE: ENABLED")
    print("CPU FALLBACK: ENABLED")
    print("AUDIO COPY: ENABLED")
    print("SUBTITLE COPY: ENABLED")
    print("OUTPUT VALIDATION: ENABLED")
    print("PARTIAL OUTPUT CLEANUP: ENABLED")


if __name__ == "__main__":
    asyncio.run(main())

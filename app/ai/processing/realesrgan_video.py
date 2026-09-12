from __future__ import annotations

import asyncio
import json
import os
import shutil
import tempfile
import time
from pathlib import Path


class RealESRGANVideoError(RuntimeError):
    pass


class RealESRGANVideoProcessor:
    """
    Real VIKKY AI video processor.

    The actual Real-ESRGAN runtime is supplied by the cloud worker
    environment. This layer handles:
      - input validation
      - frame extraction
      - Real-ESRGAN frame inference
      - frame reassembly
      - audio/subtitle preservation
      - output validation
      - cleanup

    It never reports success unless a valid video is produced.
    """

    MODES = {
        "2K_AI": (2560, 1440),
        "4K_AI": (3840, 2160),
        "8K_AI": (7680, 4320),
        "4K_HYBRID": (3840, 2160),
        "8K_HYBRID": (7680, 4320),
    }

    def __init__(self, realesrgan_script: str | None = None):
        self.ffmpeg = shutil.which("ffmpeg")
        self.ffprobe = shutil.which("ffprobe")
        self.realesrgan_script = realesrgan_script or os.getenv(
            "REALESRGAN_SCRIPT", ""
        ).strip()

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

    async def probe(self, path: str | Path) -> dict:
        if not self.ffprobe:
            raise RealESRGANVideoError("FFPROBE_NOT_FOUND")

        code, output = await self._run([
            self.ffprobe,
            "-v", "error",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            str(path),
        ])

        if code != 0:
            raise RealESRGANVideoError("INVALID_INPUT_VIDEO")

        try:
            return json.loads(output)
        except json.JSONDecodeError as exc:
            raise RealESRGANVideoError("FFPROBE_INVALID_JSON") from exc

    async def validate_input(self, path: str | Path) -> dict:
        source = Path(path)

        if not source.is_file():
            raise RealESRGANVideoError("INPUT_NOT_FOUND")

        if source.stat().st_size < 1024:
            raise RealESRGANVideoError("INPUT_TOO_SMALL")

        info = await self.probe(source)
        streams = info.get("streams", [])

        video = next(
            (s for s in streams if s.get("codec_type") == "video"),
            None,
        )

        if not video:
            raise RealESRGANVideoError("VIDEO_STREAM_NOT_FOUND")

        width = int(video.get("width") or 0)
        height = int(video.get("height") or 0)

        if width < 16 or height < 16:
            raise RealESRGANVideoError("INVALID_VIDEO_DIMENSIONS")

        return {
            "width": width,
            "height": height,
            "fps": video.get("r_frame_rate", "0/1"),
            "pix_fmt": video.get("pix_fmt"),
            "codec": video.get("codec_name"),
            "duration": float(
                info.get("format", {}).get("duration") or 0
            ),
        }

    @staticmethod
    def _scale_chain(width: int, height: int, target_w: int, target_h: int) -> list[int]:
        """
        Select practical 2x/4x Real-ESRGAN stages.

        We never ask Real-ESRGAN for an arbitrary 8x model scale.
        Final dimensions are handled by the finishing stage.
        """
        ratio = max(target_w / width, target_h / height)

        if ratio <= 1.05:
            return [1]
        if ratio <= 2.05:
            return [2]
        return [4, 2] if ratio > 4.05 else [4]

    async def process(
        self,
        input_file: str,
        output_file: str,
        mode: str,
    ) -> dict:
        started = time.time()
        mode = mode.upper().strip()

        if mode not in self.MODES:
            raise RealESRGANVideoError("UNSUPPORTED_AI_MODE")

        if not self.ffmpeg:
            raise RealESRGANVideoError("FFMPEG_NOT_FOUND")

        if not self.realesrgan_script:
            raise RealESRGANVideoError("REALESRGAN_RUNTIME_NOT_CONFIGURED")

        source = Path(input_file)
        destination = Path(output_file)
        destination.parent.mkdir(parents=True, exist_ok=True)

        source_info = await self.validate_input(source)
        target_w, target_h = self.MODES[mode]

        work_dir = Path(
            tempfile.mkdtemp(prefix="vikky_ai_", dir=str(destination.parent))
        )

        try:
            frames_in = work_dir / "frames_in"
            frames_out = work_dir / "frames_out"
            frames_in.mkdir()
            frames_out.mkdir()

            fps = source_info["fps"]

            extract_code, extract_log = await self._run([
                self.ffmpeg,
                "-hide_banner",
                "-y",
                "-i", str(source),
                "-vsync", "0",
                str(frames_in / "%08d.png"),
            ])

            if extract_code != 0:
                raise RealESRGANVideoError(
                    "FRAME_EXTRACTION_FAILED"
                )

            input_frames = sorted(frames_in.glob("*.png"))
            if not input_frames:
                raise RealESRGANVideoError("NO_FRAMES_EXTRACTED")

            scale_chain = self._scale_chain(
                source_info["width"],
                source_info["height"],
                target_w,
                target_h,
            )

            current_input = frames_in

            for stage_index, scale in enumerate(scale_chain, start=1):
                stage_output = (
                    frames_out / f"stage_{stage_index}"
                )
                stage_output.mkdir()

                command = [
                    "python",
                    self.realesrgan_script,
                    "--input",
                    str(current_input),
                    "--output",
                    str(stage_output),
                    "--outscale",
                    str(scale),
                ]

                code, log = await self._run(command)

                if code != 0:
                    raise RealESRGANVideoError(
                        f"REALESRGAN_STAGE_{stage_index}_FAILED"
                    )

                produced = sorted(stage_output.glob("*.png"))
                if len(produced) != len(input_frames):
                    raise RealESRGANVideoError(
                        f"FRAME_COUNT_MISMATCH_STAGE_{stage_index}"
                    )

                current_input = stage_output
                input_frames = produced

            final_frames = current_input

            # Final deterministic dimension finishing.
            # AI inference supplies detail; FFmpeg only fits the exact
            # requested delivery dimensions.
            final_frame_dir = frames_out / "final"
            final_frame_dir.mkdir()

            finish_code, finish_log = await self._run([
                self.ffmpeg,
                "-hide_banner",
                "-y",
                "-i", str(final_frames / "%08d.png"),
                "-vf",
                (
                    f"scale={target_w}:{target_h}:"
                    "force_original_aspect_ratio=decrease,"
                    f"pad={target_w}:{target_h}:(ow-iw)/2:(oh-ih)/2"
                ),
                "-vsync", "0",
                str(final_frame_dir / "%08d.png"),
            ])

            if finish_code != 0:
                raise RealESRGANVideoError("FINAL_FRAME_FINISH_FAILED")

            destination.unlink(missing_ok=True)

            encode_code, encode_log = await self._run([
                self.ffmpeg,
                "-hide_banner",
                "-y",
                "-framerate", fps,
                "-i", str(final_frame_dir / "%08d.png"),
                "-i", str(source),
                "-map", "0:v:0",
                "-map", "1:a?",
                "-map", "1:s?",
                "-c:v", "libx265",
                "-preset", "slow",
                "-crf", "18",
                "-pix_fmt", "yuv420p10le",
                "-c:a", "copy",
                "-c:s", "copy",
                "-max_muxing_queue_size", "4096",
                str(destination),
            ])

            if encode_code != 0:
                destination.unlink(missing_ok=True)
                raise RealESRGANVideoError("FINAL_ENCODE_FAILED")

            output_info = await self.probe(destination)

            output_video = next(
                (
                    s for s in output_info.get("streams", [])
                    if s.get("codec_type") == "video"
                ),
                None,
            )

            if not output_video:
                destination.unlink(missing_ok=True)
                raise RealESRGANVideoError(
                    "OUTPUT_VIDEO_VALIDATION_FAILED"
                )

            if (
                int(output_video.get("width") or 0) != target_w
                or int(output_video.get("height") or 0) != target_h
            ):
                destination.unlink(missing_ok=True)
                raise RealESRGANVideoError(
                    "OUTPUT_DIMENSION_VALIDATION_FAILED"
                )

            return {
                "success": True,
                "engine": "Real-ESRGAN",
                "mode": mode,
                "input": str(source),
                "output": str(destination),
                "width": target_w,
                "height": target_h,
                "frames": len(input_frames),
                "elapsed": round(time.time() - started, 2),
            }

        finally:
            shutil.rmtree(work_dir, ignore_errors=True)


async def run_realesrgan_video(
    input_file: str,
    output_file: str,
    mode: str,
) -> dict:
    return await RealESRGANVideoProcessor().process(
        input_file,
        output_file,
        mode,
    )

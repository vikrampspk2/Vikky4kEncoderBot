import json
import subprocess
from pathlib import Path


class OutputValidator:
    """Final output integrity gate."""

    @staticmethod
    def exists(path: str) -> bool:
        return Path(path).is_file() and Path(path).stat().st_size > 0

    @staticmethod
    def ffprobe(path: str) -> dict:
        if not OutputValidator.exists(path):
            raise RuntimeError("OUTPUT_MISSING_OR_EMPTY")

        result = subprocess.run(
            [
                "ffprobe",
                "-v", "error",
                "-show_format",
                "-show_streams",
                "-of", "json",
                path,
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )

        if result.returncode != 0:
            raise RuntimeError("OUTPUT_FFPROBE_FAILED")

        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise RuntimeError("OUTPUT_METADATA_INVALID") from exc

        if not data.get("streams"):
            raise RuntimeError("OUTPUT_NO_STREAMS")

        return data

    @staticmethod
    def validate_video(path: str, expected_width=None, expected_height=None):
        data = OutputValidator.ffprobe(path)

        video = next(
            (s for s in data["streams"] if s.get("codec_type") == "video"),
            None,
        )

        if not video:
            raise RuntimeError("OUTPUT_VIDEO_STREAM_MISSING")

        if expected_width and int(video.get("width", 0)) != expected_width:
            raise RuntimeError("OUTPUT_WIDTH_MISMATCH")

        if expected_height and int(video.get("height", 0)) != expected_height:
            raise RuntimeError("OUTPUT_HEIGHT_MISMATCH")

        return data

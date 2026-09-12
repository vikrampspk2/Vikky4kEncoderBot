import json
import subprocess
from pathlib import Path


class VideoAnalyzer:
    def __init__(self, ffprobe="ffprobe"):
        self.ffprobe = ffprobe

    def analyze(self, file_path):
        path = Path(file_path)

        if not path.exists():
            raise FileNotFoundError(f"Input file not found: {file_path}")

        command = [
            self.ffprobe,
            "-v", "error",
            "-show_entries",
            "format=filename,format_name,size,duration,bit_rate",
            "-show_entries",
            "stream=index,codec_type,codec_name,profile,width,height,"
            "pix_fmt,r_frame_rate,avg_frame_rate,bit_rate,channels,"
            "channel_layout,sample_rate,sample_fmt,color_space,"
            "color_transfer,color_primaries,color_range,level,"
            "codec_long_name",
            "-of", "json",
            str(path),
        ]

        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
        )

        if result.returncode != 0:
            raise RuntimeError(
                f"ffprobe failed: {result.stderr.strip()}"
            )

        data = json.loads(result.stdout)

        streams = data.get("streams", [])
        video = next(
            (s for s in streams if s.get("codec_type") == "video"),
            None,
        )

        audio = [
            s for s in streams
            if s.get("codec_type") == "audio"
        ]

        if not video:
            raise ValueError("No video stream found")

        width = video.get("width") or 0
        height = video.get("height") or 0

        return {
            "file": str(path),
            "format": data.get("format", {}),
            "video": video,
            "audio": audio,
            "audio_tracks": len(audio),
            "resolution": {
                "width": width,
                "height": height,
            },
            "is_hdr": self._detect_hdr(video),
            "is_10bit": self._detect_10bit(video),
            "source_class": self._classify(width, height),
        }

    @staticmethod
    def _detect_hdr(video):
        transfer = str(video.get("color_transfer", "")).lower()
        primaries = str(video.get("color_primaries", "")).lower()

        hdr_values = {
            "smpte2084",
            "arib-std-b67",
        }

        return transfer in hdr_values or primaries in {
            "bt2020",
            "bt2020nc",
        }

    @staticmethod
    def _detect_10bit(video):
        pix_fmt = str(video.get("pix_fmt", "")).lower()
        return "10" in pix_fmt or "12" in pix_fmt

    @staticmethod
    def _classify(width, height):
        pixels = width * height

        if pixels <= 640 * 480:
            return "very_low"

        if pixels <= 1280 * 720:
            return "low"

        if pixels <= 1920 * 1080:
            return "full_hd"

        if pixels <= 2560 * 1440:
            return "2k_or_qhd"

        if pixels <= 3840 * 2160:
            return "4k"

        return "above_4k"


def analyze_video(file_path):
    return VideoAnalyzer().analyze(file_path)

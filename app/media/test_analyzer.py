import sys
from pprint import pprint

from app.media.analyzer import analyze_video


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python -m app.media.test_analyzer <video-file>")
        raise SystemExit(1)

    result = analyze_video(sys.argv[1])

    print("VIDEO ANALYSIS OK")
    print("Resolution:", result["resolution"])
    print("Source class:", result["source_class"])
    print("Audio tracks:", result["audio_tracks"])
    print("10-bit:", result["is_10bit"])
    print("HDR:", result["is_hdr"])

    print("\nVIDEO STREAM:")
    pprint(result["video"])

    print("\nAUDIO STREAMS:")
    pprint(result["audio"])

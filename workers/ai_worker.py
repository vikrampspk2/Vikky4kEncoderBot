"""Worker contract for VIKKY Encoder.

Usage: python workers/ai_worker.py INPUT OUTPUT MODE PROFILE
This file is intentionally a safe FFmpeg fallback. Replace/extend the process_video
function with a verified/licensed AI pipeline (for example Real-ESRGAN) on a GPU host.
The contract always requires an MKV output path.
"""
import subprocess, sys
from pathlib import Path

def process_video(inp, out, mode, profile):
    out = Path(out)
    if out.suffix.lower() != '.mkv':
        raise SystemExit('Refusing non-MKV output')
    cmd=['ffmpeg','-hide_banner','-y','-i',str(inp),'-map','0','-c:v','libx265','-preset','medium','-crf','18','-pix_fmt','yuv420p10le','-c:a','copy','-c:s','copy','-c:d','copy','-f','matroska',str(out)]
    raise_code=subprocess.call(cmd)
    if raise_code: raise SystemExit(raise_code)

if __name__ == '__main__':
    if len(sys.argv)!=5: raise SystemExit('Usage: ai_worker.py INPUT OUTPUT MODE PROFILE')
    process_video(*sys.argv[1:])

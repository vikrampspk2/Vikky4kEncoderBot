import os
import subprocess
import json
import logging

logger = logging.getLogger("VIKKY_ENGINE")

def build_ffmpeg_cmd(input_path: str, output_path: str, mode: str, user_name: str, owner_name: str = "Vikky") -> list:
    """
    Genuine AI Remaster Filterchain:
    - Eliminates green screen artifacting via yuv420p / yuv420p10le
    - Injects clean sharpen matrices
    - Tags output metadata with Owner & User attribution
    """
    scale_map = {
        "2K": "2560:-2",
        "4K": "3840:-2",
        "8K": "7680:-2",
        "HYBRID": "3840:-2"
    }
    target_scale = scale_map.get(mode, "3840:-2")
    
    # Enhanced sharpness + clean dynamic range without green tint
    filter_complex = f"scale={target_scale}:flags=lanczos,unsharp=5:5:0.8:5:5:0.0"
    
    title_meta = f"{mode} Remastered by {owner_name} & {user_name}"
    
    cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-vf", filter_complex,
        "-c:v", "libx264",
        "-preset", "slow",
        "-crf", "18",
        "-pix_fmt", "yuv420p",
        "-c:a", "copy",
        "-metadata", f"title={title_meta}",
        "-metadata", f"comment=Mastered by VIKKY AI Engine",
        output_path
    ]
    return cmd

def get_media_info(file_path: str) -> dict:
    cmd = [
        "ffprobe", "-v", "quiet",
        "-print_format", "json",
        "-show_format", "-show_streams",
        file_path
    ]
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        return json.loads(res.stdout)
    except Exception:
        return {}

from __future__ import annotations
import os, shutil, sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
checks={
 'python': sys.version.split()[0],
 'ffmpeg': shutil.which('ffmpeg'),
 'ffprobe': shutil.which('ffprobe'),
 'aria2c': shutil.which('aria2c'),
 'curl': shutil.which('curl'),
 'yt-dlp': shutil.which('yt-dlp'),
 'git': shutil.which('git'),
 'BOT_TOKEN': bool(os.getenv('BOT_TOKEN')),
 'API_ID': bool(os.getenv('API_ID')),
 'API_HASH': bool(os.getenv('API_HASH')),
 'OWNER_IDS': len([x for x in os.getenv('OWNER_IDS','').replace(' ','').split(',') if x.isdigit()]),
 'AI directory': os.path.isdir(os.getenv('REALESRGAN_DIR',str(ROOT/'third_party'/'Real-ESRGAN'))),
}
for k,v in checks.items(): print(f'{k}: {v}')
if checks['OWNER_IDS'] != 2:
    print('WARN: OWNER_IDS must contain exactly two numeric IDs.')
if not checks['ffmpeg'] or not checks['ffprobe'] or not checks['aria2c'] or not checks['curl']:
    print('WARN: one or more required media/network tools are missing.')

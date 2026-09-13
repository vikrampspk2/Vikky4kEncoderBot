"""Kaggle GPU worker template.

This file is intentionally standalone: Kaggle credentials stay outside Git.
It downloads a public/direct source URL, runs the real Real-ESRGAN video
inference script on the Kaggle GPU, then uploads the resulting MKV using the
same guest uploader path used by the bot.
"""
from __future__ import annotations
import os, subprocess, sys
from pathlib import Path

URL=os.environ['VIKKY_SOURCE_URL']
OUTPUT=os.environ.get('VIKKY_OUTPUT','/kaggle/working/result.mkv')
PROFILE=os.environ.get('VIKKY_PROFILE','4K_AI')

subprocess.run(['aria2c','-c','-x','16','-s','16','-k','1M','--file-allocation=none','--out','/kaggle/working/input','--dir','/kaggle/working',URL],check=True)
input_path=Path('/kaggle/working/input')
script=Path('/kaggle/working/Real-ESRGAN/inference_realesrgan_video.py')
# Clone/install Real-ESRGAN in the Kaggle notebook image before running this template.
subprocess.run([sys.executable,str(script),'-i',str(input_path),'-n',os.getenv('VIKKY_AI_MODEL','realesr-general-x4v3'),'-o','/kaggle/working/ai','-s',os.getenv('VIKKY_AI_SCALE','4')],check=True)
print('Kaggle AI render complete. Upload /kaggle/working/ai/*.mp4 with the guest uploader adapter and return its URL to the bot.')

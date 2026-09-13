from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

PROFILES = {
    '2K_AI': 1440,
    '4K_AI': 2160,
    '8K_AI': 4320,
    '4K_HYBRID': 2160,
    '8K_HYBRID': 4320,
}


def probe_size(path: Path):
    p = subprocess.run(['ffprobe','-v','error','-select_streams','v:0','-show_entries','stream=width,height','-of','csv=p=0:s=x',str(path)], capture_output=True, text=True, check=True)
    w,h = map(int,p.stdout.strip().split('x'))
    return w,h


def run(cmd):
    print('VIKKY_AI_CMD ' + ' '.join(map(str,cmd)), flush=True)
    return subprocess.call(cmd)


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--input',required=True)
    ap.add_argument('--output',required=True)
    ap.add_argument('--profile',required=True)
    ap.add_argument('--realesrgan-dir',default=os.getenv('REALESRGAN_DIR',''))
    ap.add_argument('--model',default=os.getenv('VIKKY_AI_MODEL','realesr-general-x4v3'))
    ap.add_argument('--tile',default=os.getenv('VIKKY_AI_TILE','0'))
    ap.add_argument('--processes',default=os.getenv('VIKKY_AI_PROCESSES','1'))
    args=ap.parse_args()
    inp=Path(args.input); out=Path(args.output); out.parent.mkdir(parents=True,exist_ok=True)
    if not inp.exists(): raise SystemExit('Input does not exist')
    script=Path(args.realesrgan_dir)/'inference_realesrgan_video.py'
    if not script.exists():
        raise SystemExit('Real-ESRGAN video script not found. Set REALESRGAN_DIR to the official Real-ESRGAN checkout.')
    ffmpeg=shutil.which('ffmpeg')
    ffprobe=shutil.which('ffprobe')
    if not ffmpeg or not ffprobe: raise SystemExit('ffmpeg/ffprobe are required')
    w,h=probe_size(inp); target=PROFILES.get(args.profile)
    if not target: raise SystemExit(f'Unsupported AI profile: {args.profile}')
    # Real-ESRGAN performs the neural super-resolution stage. Its x4 models are used
    # at the largest useful scale, then FFmpeg makes only the final exact target-size fit.
    scale=min(4.0,max(1.0,target/max(h,1)))
    if scale <= 1.01:
        scale=1.0
    work=out.parent/(out.stem+'.ai')
    work.mkdir(parents=True,exist_ok=True)
    ai_out=work/(inp.stem+'_ai.mp4')
    if scale > 1.01:
        cmd=[sys.executable,str(script),'-i',str(inp),'-n',args.model,'-o',str(work),'-s',str(scale),'--suffix','ai','-t',str(args.tile),'--num_process_per_gpu',str(args.processes)]
        rc=run(cmd)
        if rc!=0 or not ai_out.exists(): raise SystemExit(f'Real-ESRGAN failed with exit code {rc}')
        source=ai_out
    else:
        source=inp
    vf=f'scale=-2:{target}:flags=lanczos'
    if args.profile.endswith('HYBRID'):
        vf += ',hqdn3d=1.0:1.0:3:3,unsharp=5:5:0.7:3:3:0.0,eq=contrast=1.04:saturation=1.08'
    cmd=[ffmpeg,'-hide_banner','-y','-i',str(source),'-map','0','-vf',vf,'-c:v','libx265','-preset','medium','-crf','16','-pix_fmt','yuv420p10le','-c:a','copy','-c:s','copy','-c:d','copy','-f','matroska',str(out)]
    rc=run(cmd)
    shutil.rmtree(work,ignore_errors=True)
    if rc!=0 or not out.exists() or out.stat().st_size==0: raise SystemExit(f'Final MKV encode failed with exit code {rc}')
    print('VIKKY_AI_DONE',flush=True)

if __name__=='__main__': main()

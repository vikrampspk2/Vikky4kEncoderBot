# VIKKY Encoder — Production Hardened Build

This package is the hardened continuation of the VIKKY Encoder bot. It is designed around:

- Hydrogram with Telegram parsing disabled (prevents dynamic Markdown/HTML entity errors).
- Direct HTTP(S) source URLs: `aria2c` first, then `curl`, then `yt-dlp` when a site/extractor is required.
- `ffprobe` validation before a URL becomes a job.
- Persistent SQLite queue and restart recovery.
- 60 GB input ceiling by default.
- Real AI profiles only when a real AI worker is installed/configured. The bot never labels a Lanczos resize as AI.
- Real-ESRGAN video worker support for GPU upscaling.
- External guest uploader fallback: Buzzheavier first; storage.to for files up to its current 25 GB anonymous limit.
- 15 uploader slots are preserved in `config/uploaders.json`; unsupported/unverified slots are disabled rather than pretending they work.
- Output flow: PROCESS → VALIDATE → UPLOAD → LINK → USER/CHANNEL → CLEANUP.
- Manual payment verification, exactly two owners, persistent access/entitlements, weekly quota reset at Saturday 00:00 Asia/Kolkata.

## Important truth about “100%”

No software can guarantee every arbitrary Internet URL, CDN, signed URL, GPU, hosting provider, or external service will never fail. A direct URL that requires cookies, authentication, geo access, or a short-lived signature cannot be downloaded from the URL alone. The downloader therefore retries and falls back, but reports a real failure instead of faking success.

Likewise, AI upscaling is not magically created by FFmpeg scaling. `2K_AI/4K_AI/8K_AI` require the Real-ESRGAN worker (or your own configured AI worker). If it is missing, the job fails clearly rather than silently producing a fake AI result.

## 1. System packages

Linux/Ubuntu example:

```bash
sudo apt update
sudo apt install -y ffmpeg aria2 curl python3 python3-venv git
```

`yt-dlp` can be installed by pip or from its official release.

## 2. Python bot environment

Use the bot's Python environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip wheel
pip install -r requirements.txt
```

The bot code is syntax-tested here, but actual Telegram/GPU/provider E2E testing must be performed on the deployment machine because those services and credentials are external.

## 3. Secrets

Copy `.env.example` to `.env` for a private server, or use GitHub Secrets/environment variables. Never put real tokens in Git.

Required:

- `BOT_TOKEN`
- `API_ID`
- `API_HASH`
- exactly two comma-separated `OWNER_IDS`

Kaggle credentials are also secrets. Current Kaggle tooling supports `KAGGLE_API_TOKEN` or legacy `~/.kaggle/kaggle.json`; do not commit either form.

## 4. Real AI GPU setup

The supported open-source AI path is Real-ESRGAN. The official project provides a video inference script and GPU/CPU paths. Clone it outside the Git repository, then set:

```bash
git clone https://github.com/xinntao/Real-ESRGAN.git third_party/Real-ESRGAN
export REALESRGAN_DIR="$PWD/third_party/Real-ESRGAN"
```

The AI Python stack is best isolated from the Telegram bot environment (for example a Python 3.11/3.12 GPU environment) because PyTorch/GPU wheels may lag the newest Python release.

For an NVIDIA GPU, install a matching PyTorch/CUDA build and the Real-ESRGAN dependencies in that AI environment. The bot itself does not download proprietary Topaz software or fake a Topaz result.

For NVIDIA/AMD/Intel GPU systems where Vulkan is preferable, the official Real-ESRGAN NCNN Vulkan executable is another real GPU path. It can process image directories, while the supplied Python video worker is the default integration.

## 5. Kaggle GPU

Kaggle is kept as an external GPU worker option. Put the token in the environment/GitHub Secrets, never in source. `workers/kaggle_worker_template.py` shows the standalone worker contract: direct source URL → real AI render → external upload → return link.

For two Kaggle accounts, keep credentials in separate secrets such as `KAGGLE_API_TOKEN_1` and `KAGGLE_API_TOKEN_2`. Rotation/orchestration must obey Kaggle's current quotas and terms; the package does not bypass those limits.

## 6. Direct URL behavior

For ordinary direct video URLs, the order is:

1. aria2c with resume + 16 connections/splits.
2. curl HTTPS fallback.
3. yt-dlp for extractor sites/manifests when needed.
4. ffprobe video-stream validation.

A URL ending in `.mp4` is not required. A CDN can return video bytes without a video extension; the bot validates the downloaded bytes.

## 7. 50–60 GB outputs

Telegram is not used as the final transport for giant outputs. The bot uploads the completed MKV to an external host and sends the download URL. Buzzheavier is the large-file guest path in this build. storage.to is enabled only for files within its current anonymous 25 GB file-size limit.

## 8. 24/7

For a real 24/7 server, use the included systemd service or Docker restart policy. GitHub-hosted Actions runners are not designed to be a permanent 24/7 service; use a VPS or self-hosted runner for continuous operation.

```bash
cp deploy/systemd/vikky-encoder.service.example /etc/systemd/system/vikky-encoder.service
# edit User= and WorkingDirectory=
sudo systemctl daemon-reload
sudo systemctl enable --now vikky-encoder
sudo journalctl -u vikky-encoder -f
```

## 9. Security rules

- Two owners only: enforced by `OWNER_IDS` count.
- Secrets stay in environment/GitHub Secrets.
- Payment proofs are only routed to owners and are not logged as image contents.
- Dynamic Telegram text uses `ParseMode.DISABLED`.
- User input is not interpolated into shell commands except through controlled quoting in the AI worker command builder.
- Do not give uploaders owner/admin credentials.
- Keep uploader API keys, if ever added, in secrets—not `config/uploaders.json`.

## 10. Smoke checks

```bash
python -m py_compile main.py workers/*.py config/*.py uploaders/*.py
python scripts/doctor.py
python -m pytest -q
```

Then start the bot and run `/health` as an owner.

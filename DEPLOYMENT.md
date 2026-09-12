# Deployment — GitHub Actions / VPS

## GitHub Secrets
Set, at minimum:
- `BOT_TOKEN`
- `OWNER_IDS` (exactly two IDs)
- any worker/provider credentials needed by your real deployment

Do NOT commit `.env`, tokens, API keys, OAuth secrets, or Kaggle credentials.
Rotate any credential that was previously exposed.

## Python
1. Install Python 3.11+ and FFmpeg/FFprobe on the runtime host.
2. `python -m venv .venv && source .venv/bin/activate`
3. `pip install -r requirements.txt`
4. Export secrets or load `.env` with your process manager.
5. Run `python main.py`.

## 24/7
Use an always-on VPS/server, container platform, or equivalent. Android/Termux is suitable for setup/testing but is not a guaranteed 24/7 control plane.

A GitHub Actions workflow can validate/build the package, but a normal Actions runner is not a reliable permanent Telegram polling server. For 24/7, use a persistent host.

## AI
Set `VIKKY_WORKER_CMD` to your verified GPU worker. The worker receives input/output/mode/profile. It must create the exact output path and keep it `.mkv`.

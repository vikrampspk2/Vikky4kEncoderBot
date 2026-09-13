# Security checklist

1. Rotate any old leaked Telegram/Kaggle credentials before deployment.
2. Put `BOT_TOKEN`, `API_ID`, `API_HASH`, owner IDs and Kaggle credentials in GitHub Secrets or a private `.env` outside Git.
3. Never paste secrets into issues, logs, screenshots, README files or source code.
4. Keep exactly two owner IDs in `OWNER_IDS`.
5. Use guest uploaders unless an authenticated provider is explicitly configured through environment secrets.
6. Do not grant uploader users owner/admin capabilities.
7. Review the output link before distributing copyrighted/private media.
8. Keep OS/GPU drivers and FFmpeg updated.

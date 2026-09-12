# Official-source design notes

Google Drive: resumable uploads are intended for large/interrupted uploads; Drive has quotas and a 5 TB maximum file size.
OneDrive: Microsoft Graph supports resumable upload sessions for large files.
Cloudflare R2: multipart uploads support resumability/parallelism and objects up to 5 TiB.
Backblaze B2: authenticated upload APIs support large-file workflows.
Browser playback: HTML5 playback depends on the provider supporting range/streaming and browser codec support. MKV is not universally browser-playable, so an MP4/H.264/AAC derivative is recommended for web playback.

Security: secrets must stay in environment/cloud-secret storage, never source code.

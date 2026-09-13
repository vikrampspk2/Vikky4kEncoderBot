from __future__ import annotations

import asyncio
import os
import re
import shutil
from pathlib import Path
from urllib.parse import urlparse

URL_RE = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)
VIDEO_EXTS = {".mp4", ".mkv", ".webm", ".mov", ".avi", ".m4v", ".ts", ".m2ts", ".mts", ".flv", ".3gp"}
VIDEO_SITES = (
    "youtube.", "youtu.be", "twitter.com", "x.com", "instagram.com", "facebook.com",
    "tiktok.com", "vimeo.com", "dailymotion.com", "twitch.tv", "reddit.com",
    "streamable.com", "bilibili.com", "nicovideo.jp", "rumble.com"
)
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/131 Safari/537.36 VIKKY-Downloader/1.0"


def extract_url(text: str | None) -> str | None:
    if not text:
        return None
    m = URL_RE.search(text)
    return m.group(0).rstrip(".,);]}") if m else None


def _looks_like_video_site(url: str) -> bool:
    host = urlparse(url).netloc.lower().split(":", 1)[0]
    return any(x in host for x in VIDEO_SITES)


def _looks_like_direct_media(url: str) -> bool:
    return Path(urlparse(url).path.lower()).suffix in VIDEO_EXTS


async def _run(cmd: list[str], *, output_path: Path | None = None, timeout: int | None = None,
               progress_cb=None) -> tuple[int, str]:
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    log: list[str] = []
    last_report = 0.0
    try:
        while True:
            try:
                raw = await asyncio.wait_for(proc.stdout.readline(), timeout=1.0)
            except asyncio.TimeoutError:
                raw = b""
            if raw:
                line = raw.decode("utf-8", "ignore").strip()
                if line:
                    log.append(line)
            if output_path and output_path.exists() and progress_cb:
                now = asyncio.get_running_loop().time()
                if now - last_report >= 4:
                    last_report = now
                    size = output_path.stat().st_size
                    if size:
                        try:
                            await progress_cb(f"Download in progress: {size / 1024**2:.1f} MB")
                        except Exception:
                            pass
            if proc.returncode is not None:
                break
            try:
                await asyncio.wait_for(proc.wait(), timeout=0.05)
                break
            except asyncio.TimeoutError:
                pass
        if proc.returncode is None:
            await proc.wait()
    except asyncio.CancelledError:
        try:
            proc.kill()
        except Exception:
            pass
        await proc.wait()
        raise
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass
        await proc.wait()
        raise
    return proc.returncode, "\n".join(log)[-16000:]


async def _validate_media(path: Path) -> bool:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe or not path.exists() or path.stat().st_size <= 0:
        return False
    proc = await asyncio.create_subprocess_exec(
        ffprobe, "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=codec_name", "-of", "default=nw=1:nk=1", str(path),
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    out, _ = await proc.communicate()
    return proc.returncode == 0 and bool(out.strip())


async def download_url(
    url: str,
    destination: str | Path,
    *,
    max_bytes: int = 60 * 1024**3,
    progress_cb=None,
) -> Path:
    """Download an HTTP(S) media URL robustly.

    Order:
      1. aria2c for ordinary direct HTTP(S) files
      2. curl as a generic HTTP fallback for signed/CDN URLs
      3. yt-dlp for extractor sites and any URL the first two methods cannot handle

    The file is accepted only after ffprobe confirms a video stream.
    """
    if not re.match(r"^https?://", url, re.I):
        raise ValueError("Only HTTP(S) URLs are accepted")

    dest = Path(destination)
    dest.parent.mkdir(parents=True, exist_ok=True)
    stem = dest.with_suffix("")
    errors: list[str] = []

    aria2c = shutil.which("aria2c")
    curl = shutil.which("curl")
    ytdlp = shutil.which("yt-dlp") or shutil.which("yt_dlp")

    async def status(msg: str):
        if progress_cb:
            try:
                await progress_cb(msg)
            except Exception:
                pass

    # Site extractors should go directly to yt-dlp; aria2c would otherwise download HTML.
    if aria2c and not _looks_like_video_site(url):
        source = dest.parent / (stem.name + ".aria2.source")
        source.unlink(missing_ok=True)
        cmd = [
            aria2c, "-c", "-x", "16", "-s", "16", "-k", "1M",
            "--max-tries=5", "--retry-wait=3", "--connect-timeout=20", "--timeout=60",
            "--file-allocation=none", "--allow-overwrite=true", "--auto-file-renaming=false",
            "--check-certificate=true", "--summary-interval=1", "--console-log-level=warn",
            "--user-agent", UA, "--dir", str(source.parent), "--out", source.name, url,
        ]
        await status("Downloading with aria2c (16 connections)...")
        rc, log = await _run(cmd, output_path=source, progress_cb=progress_cb)
        if rc == 0 and source.exists() and source.stat().st_size > 0:
            if source.stat().st_size > max_bytes:
                source.unlink(missing_ok=True)
                raise RuntimeError("Downloaded input exceeds the configured size limit")
            if await _validate_media(source):
                source.replace(dest)
                await status("Download complete and media validated.")
                return dest
            errors.append("aria2c downloaded a non-video response")
            source.unlink(missing_ok=True)
        else:
            errors.append("aria2c failed: " + log[-1800:])

    # Generic CDN/direct-link fallback. This handles URLs without a video extension.
    if curl and not _looks_like_video_site(url):
        source = dest.parent / (stem.name + ".curl.source")
        source.unlink(missing_ok=True)
        cmd = [
            curl, "-L", "--fail", "--retry", "4", "--retry-delay", "2",
            "--connect-timeout", "20", "-A", UA, "-o", str(source), url,
        ]
        await status("Direct HTTP download fallback starting...")
        rc, log = await _run(cmd, output_path=source, progress_cb=progress_cb)
        if rc == 0 and source.exists() and source.stat().st_size > 0:
            if source.stat().st_size > max_bytes:
                source.unlink(missing_ok=True)
                raise RuntimeError("Downloaded input exceeds the configured size limit")
            if await _validate_media(source):
                source.replace(dest)
                await status("Download complete and media validated.")
                return dest
            errors.append("curl returned a non-video response")
            source.unlink(missing_ok=True)
        else:
            errors.append("curl failed: " + log[-1800:])

    # yt-dlp handles websites, HLS/DASH manifests and many signed media pages.
    if ytdlp:
        await status("Trying yt-dlp extractor/stream download...")
        cmd = [
            ytdlp, "--no-playlist", "--retries", "5", "--fragment-retries", "5",
            "--socket-timeout", "30", "--newline", "-f", "bv*+ba/b",
            "--merge-output-format", "mkv", "--no-mtime", "-o", str(dest), url,
        ]
        rc, log = await _run(cmd, output_path=dest, progress_cb=progress_cb)
        if rc == 0 and dest.exists() and dest.stat().st_size > 0:
            if dest.stat().st_size > max_bytes:
                dest.unlink(missing_ok=True)
                raise RuntimeError("Downloaded input exceeds the configured size limit")
            if await _validate_media(dest):
                await status("Download complete and media validated.")
                return dest
        errors.append("yt-dlp failed: " + log[-3000:])

    raise RuntimeError("URL download failed. " + " | ".join(errors)[-5000:])

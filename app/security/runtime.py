import hashlib
import os
import re
import secrets
from pathlib import Path


SECRET_KEYS = (
    "TOKEN", "KEY", "PASSWORD", "SECRET", "API_KEY"
)


def sanitize_filename(name: str, fallback: str = "output.mkv") -> str:
    name = Path(str(name)).name
    name = re.sub(r"[^A-Za-z0-9._ -]", "_", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name[:180] or fallback


def safe_job_id() -> str:
    return "VIKKY-" + secrets.token_hex(10).upper()


def secret_present(name: str) -> bool:
    return bool(os.getenv(name))


def redacted_environment() -> dict:
    result = {}
    for key, value in os.environ.items():
        upper = key.upper()
        if any(marker in upper for marker in SECRET_KEYS):
            result[key] = "***REDACTED***"
        else:
            result[key] = value
    return result


def file_sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

from __future__ import annotations

import json
from pathlib import Path

from .adapters import upload

BASE = Path(__file__).resolve().parents[1]
CONFIG = BASE / 'config' / 'uploaders.json'


def _slots():
    try:
        return json.loads(CONFIG.read_text(encoding='utf-8')).get('slots', [])
    except Exception:
        return []


def upload_with_fallback(path: str) -> dict:
    p = Path(path)
    size = p.stat().st_size
    errors = []
    for slot in _slots():
        if not slot.get('enabled'):
            continue
        max_bytes = int(slot.get('max_bytes') or 0)
        if max_bytes and size > max_bytes:
            continue
        name = slot.get('name', '')
        if name not in {'buzzheavier', 'storage_to'}:
            continue
        try:
            result = upload(p, name)
            if result.get('url', '').startswith(('http://', 'https://')):
                return result
            errors.append(f'{name}: invalid URL')
        except Exception as exc:
            errors.append(f'{name}: {type(exc).__name__}: {exc}')
    raise RuntimeError('All configured uploaders failed. ' + ' | '.join(errors)[-5000:])

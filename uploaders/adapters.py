from __future__ import annotations

import json
import mimetypes
import os
import secrets
import string
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

UA = 'VIKKY-Encoder/1.0 (+guest-uploader)'
TIMEOUT = (30, 300)


def _safe_filename(path: Path) -> str:
    name = path.name.replace('\\', '_').replace('/', '_')
    return ''.join(c if c.isalnum() or c in '._- ' else '_' for c in name)[:500] or 'output.mkv'


def upload_buzzheavier(path: str | Path) -> dict:
    p = Path(path)
    name = _safe_filename(p)
    url = 'https://w.buzzheavier.com/' + requests.utils.quote(name, safe='._- ')
    with p.open('rb') as f:
        r = requests.put(url, data=f, headers={'User-Agent': UA, 'Content-Type': 'application/octet-stream'}, timeout=TIMEOUT)
    r.raise_for_status()
    text = r.text.strip()
    # Buzzheavier may return a URL in the body; also accept JSON/url fields.
    try:
        obj = r.json()
        for key in ('url', 'download_url', 'link'):
            if obj.get(key):
                return {'provider': 'buzzheavier', 'url': str(obj[key])}
    except Exception:
        pass
    for token in text.replace('"', ' ').split():
        if token.startswith('http://') or token.startswith('https://'):
            return {'provider': 'buzzheavier', 'url': token.strip(' ,')}
    # Known public download route fallback when the API response is empty.
    return {'provider': 'buzzheavier', 'url': url.replace('w.buzzheavier.com', 'buzzheavier.com')}


def _visitor_token() -> str:
    return secrets.token_urlsafe(32)


def upload_storage_to(path: str | Path) -> dict:
    p = Path(path)
    size = p.stat().st_size
    if size > 25 * 1024**3:
        raise ValueError('storage.to anonymous max file size is 25 GB')
    visitor = _visitor_token()
    headers = {'X-Visitor-Token': visitor, 'Content-Type': 'application/json', 'User-Agent': UA}
    mime = mimetypes.guess_type(p.name)[0] or 'application/octet-stream'
    init = requests.post('https://storage.to/api/upload/init', headers=headers, json={
        'filename': p.name[:255], 'content_type': mime, 'size': size
    }, timeout=TIMEOUT)
    init.raise_for_status()
    data = init.json()
    if not data.get('success'):
        raise RuntimeError(f'storage.to init failed: {data}')
    typ = data.get('type')
    if typ == 'single':
        with p.open('rb') as fh:
            extra = {}
            for k, v in (data.get('headers') or {}).items():
                extra[k] = v[0] if isinstance(v, list) and v else v
            extra['User-Agent'] = UA
            up = requests.put(data['upload_url'], headers=extra, data=fh, timeout=TIMEOUT)
        up.raise_for_status()
    elif typ == 'multipart':
        upload_id = data['upload_id']
        part_size = int(data['part_size'])
        total = (size + part_size - 1) // part_size
        urls = {int(k): v for k, v in (data.get('initial_urls') or {}).items()}
        missing = [n for n in range(1, total + 1) if n not in urls]
        if missing:
            rr = requests.post('https://storage.to/api/upload/parts', headers=headers, json={'upload_id': upload_id, 'part_numbers': missing}, timeout=TIMEOUT)
            rr.raise_for_status()
            for item in rr.json().get('part_urls', []):
                urls[int(item['partNumber'])] = item['url']
        if len(urls) != total:
            raise RuntimeError('storage.to did not return all multipart URLs')

        def put_part(n: int):
            start = (n - 1) * part_size
            length = min(part_size, size - start)
            with p.open('rb') as f:
                f.seek(start)
                body = f.read(length)
            rr = requests.put(urls[n], data=body, headers={'User-Agent': UA}, timeout=TIMEOUT)
            rr.raise_for_status()
            return {'partNumber': n, 'etag': rr.headers.get('ETag', '').strip()}

        parts = []
        with ThreadPoolExecutor(max_workers=4) as pool:
            futs = [pool.submit(put_part, n) for n in range(1, total + 1)]
            for fut in as_completed(futs):
                parts.append(fut.result())
        parts.sort(key=lambda x: x['partNumber'])
        if any(not x['etag'] for x in parts):
            raise RuntimeError('storage.to multipart upload did not return ETags')
        done = requests.post('https://storage.to/api/upload/complete-multipart', headers=headers, json={'upload_id': upload_id, 'parts': parts}, timeout=TIMEOUT)
        done.raise_for_status()
    else:
        raise RuntimeError(f'Unsupported storage.to upload type: {typ}')

    confirm = requests.post('https://storage.to/api/upload/confirm', headers=headers, json={
        'filename': p.name[:255], 'size': size, 'content_type': mime, 'r2_key': data['r2_key']
    }, timeout=TIMEOUT)
    confirm.raise_for_status()
    result = confirm.json()
    file_obj = result.get('file') or {}
    share = file_obj.get('url')
    if not share:
        raise RuntimeError(f'storage.to confirm failed: {result}')
    return {'provider': 'storage.to', 'url': share, 'expires_at': file_obj.get('expires_at', '')}


def upload(path: str | Path, provider: str) -> dict:
    p = Path(path)
    if provider == 'buzzheavier':
        return upload_buzzheavier(p)
    if provider == 'storage_to':
        return upload_storage_to(p)
    raise ValueError(f'Provider {provider} is not implemented/enabled')

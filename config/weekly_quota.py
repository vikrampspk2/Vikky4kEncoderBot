from __future__ import annotations
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

IST = ZoneInfo('Asia/Kolkata')


def _week_start_ts(now: int | None = None) -> int:
    dt = datetime.fromtimestamp(now or __import__('time').time(), tz=timezone.utc).astimezone(IST)
    # Saturday 00:00 local time is the reset boundary.
    days_since_sat = (dt.weekday() - 5) % 7
    start = (dt - timedelta(days=days_since_sat)).replace(hour=0, minute=0, second=0, microsecond=0)
    return int(start.timestamp())


def ensure_schema(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS quota_usage (
        uid INTEGER NOT NULL,
        week_start INTEGER NOT NULL,
        used_bytes INTEGER NOT NULL DEFAULT 0,
        used_tasks INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY(uid, week_start)
    )''')


def get_usage(conn, uid: int, now: int | None = None):
    ws = _week_start_ts(now)
    row = conn.execute('SELECT used_bytes, used_tasks FROM quota_usage WHERE uid=? AND week_start=?', (uid, ws)).fetchone()
    if not row:
        return {'week_start': ws, 'used_bytes': 0, 'used_tasks': 0}
    return {'week_start': ws, 'used_bytes': int(row[0]), 'used_tasks': int(row[1])}


def can_consume(conn, uid: int, bytes_needed: int, max_bytes: int, max_tasks: int, now: int | None = None) -> bool:
    u = get_usage(conn, uid, now)
    return u['used_bytes'] + int(bytes_needed) <= int(max_bytes) and u['used_tasks'] + 1 <= int(max_tasks)


def consume(conn, uid: int, bytes_used: int, now: int | None = None):
    ws = _week_start_ts(now)
    conn.execute('''INSERT INTO quota_usage(uid,week_start,used_bytes,used_tasks) VALUES(?,?,?,1)
                    ON CONFLICT(uid,week_start) DO UPDATE SET used_bytes=used_bytes+excluded.used_bytes, used_tasks=used_tasks+1''',
                 (uid, ws, int(bytes_used)))
    conn.commit()

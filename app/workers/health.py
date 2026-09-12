from datetime import datetime, timezone

def worker_health(worker_id: str) -> dict:
    return {
        "worker_id": worker_id,
        "status": "ready",
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }

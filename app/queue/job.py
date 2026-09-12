from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass
class Job:
    job_id: str
    user_id: int
    mode: str
    input_path: str
    output_path: Optional[str] = None
    target_size_gb: Optional[float] = None
    status: str = "queued"
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

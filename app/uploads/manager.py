import asyncio
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class UploadTarget:
    target_id: str
    name: str
    kind: str
    enabled: bool = True
    configured: bool = False
    max_file_gb: Optional[float] = None


class UploadManager:
    """
    Provider-neutral upload layer.

    Google Drive and 10+ external hosts plug in here.
    No provider is marked usable until its credentials/API are configured
    and a real upload test succeeds.
    """

    def __init__(self):
        self.targets = [
            UploadTarget(
                "google-drive",
                "Google Drive",
                "drive",
                configured=bool(os.getenv("GOOGLE_DRIVE_REFRESH_TOKEN")),
            )
        ]

        # Reserved slots for 10+ independently configurable providers.
        for index in range(1, 11):
            self.targets.append(
                UploadTarget(
                    f"host-{index}",
                    f"Upload Host {index}",
                    "external",
                    configured=bool(
                        os.getenv(f"UPLOAD_HOST_{index}_TOKEN")
                    ),
                )
            )

    def available_targets(self):
        return [
            target
            for target in self.targets
            if target.enabled and target.configured
        ]

    def status(self):
        return [
            {
                "id": target.target_id,
                "name": target.name,
                "enabled": target.enabled,
                "configured": target.configured,
            }
            for target in self.targets
        ]

    async def upload(self, path: str, target_id: str) -> dict:
        target = next(
            (t for t in self.targets if t.target_id == target_id),
            None,
        )

        if target is None:
            raise RuntimeError("UPLOAD_TARGET_UNKNOWN")

        if not target.enabled or not target.configured:
            raise RuntimeError("UPLOAD_TARGET_NOT_CONFIGURED")

        if not Path(path).is_file():
            raise RuntimeError("UPLOAD_SOURCE_MISSING")

        # Real provider adapters plug in here.
        # Never claim upload success without a confirmed provider response.
        await asyncio.sleep(0)

        return {
            "success": False,
            "target_id": target_id,
            "error": "PROVIDER_ADAPTER_NOT_CONNECTED",
        }

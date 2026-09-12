import asyncio
import base64
import os
import time
from dataclasses import dataclass
from typing import Optional

import requests


KAGGLE_BASE = "https://www.kaggle.com/api/v1"


@dataclass
class KaggleRun:
    success: bool
    kernel_id: str
    status: str
    error: Optional[str] = None
    retryable: bool = False


class KaggleAPI:
    """
    Secure Kaggle API connector.

    No credentials are printed.
    No API response is treated as GPU success.
    GPU availability is verified by the remote worker itself.
    """

    def __init__(self, username: str, api_key: str):
        if not username or not api_key:
            raise ValueError("KAGGLE_CREDENTIALS_MISSING")

        self.username = username
        self.api_key = api_key
        self.timeout = 30

    def _headers(self):
        raw = f"{self.username}:{self.api_key}".encode()
        token = base64.b64encode(raw).decode()

        return {
            "Authorization": f"Basic {token}",
            "Content-Type": "application/json",
        }

    def request(self, method: str, path: str, **kwargs):
        url = f"{KAGGLE_BASE}{path}"

        response = requests.request(
            method,
            url,
            headers=self._headers(),
            timeout=self.timeout,
            **kwargs,
        )

        if response.status_code in (401, 403):
            raise RuntimeError("KAGGLE_AUTH_FAILED")

        if response.status_code == 429:
            raise RuntimeError("KAGGLE_RATE_LIMITED")

        response.raise_for_status()
        return response

    def connectivity_test(self) -> bool:
        response = self.request(
            "GET",
            "/datasets/list",
            params={"maxSize": 1},
        )
        return response.status_code == 200

    async def connectivity_test_async(self) -> bool:
        return await asyncio.to_thread(
            self.connectivity_test
        )


def load_account(number: int):
    username = os.getenv(f"KAGGLE{number}_USERNAME")
    key = os.getenv(f"KAGGLE{number}_KEY")

    return KaggleAPI(username, key)


async def test():
    print("=== VIKKY KAGGLE API CONNECTOR ===")

    for number in (1, 2):
        try:
            api = load_account(number)
            ok = await api.connectivity_test_async()

            print(
                f"KAGGLE-{number}: "
                f"API_REACHABLE={ok}"
            )

        except Exception as exc:
            print(
                f"KAGGLE-{number}: "
                f"ERROR={type(exc).__name__}"
            )

    print("SECRET EXPOSURE: BLOCKED")
    print("GPU SUCCESS CLAIM: BLOCKED")


if __name__ == "__main__":
    asyncio.run(test())

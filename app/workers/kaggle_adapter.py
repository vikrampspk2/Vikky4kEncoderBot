import asyncio
import base64
import time
from dataclasses import dataclass
from typing import Optional

import requests

from config.settings import (
    KAGGLE1_USERNAME,
    KAGGLE1_KEY,
    KAGGLE2_USERNAME,
    KAGGLE2_KEY,
)


KAGGLE_API = "https://www.kaggle.com/api/v1/datasets/list"


@dataclass
class KaggleAccount:
    account_id: str
    username: str
    key: str
    reachable: bool = False
    last_check: float = 0.0
    error: Optional[str] = None


class KaggleGPUAdapter:
    """
    VIKKY Kaggle GPU adapter.

    Responsibilities:
      - Securely load credentials from settings/.env
      - Check Kaggle API reachability
      - Track account health
      - Never expose API keys in logs
      - Provide GPU availability state to the worker controller

    IMPORTANT:
      API reachability != proof of an available Kaggle GPU session.
      Actual GPU execution/quota handling is connected in the execution layer.
    """

    def __init__(self):
        self.accounts = [
            KaggleAccount(
                account_id="kaggle-1",
                username=KAGGLE1_USERNAME,
                key=KAGGLE1_KEY,
            ),
            KaggleAccount(
                account_id="kaggle-2",
                username=KAGGLE2_USERNAME,
                key=KAGGLE2_KEY,
            ),
        ]

    @staticmethod
    def _auth_header(username: str, key: str) -> str:
        raw = f"{username}:{key}".encode()
        encoded = base64.b64encode(raw).decode()
        return f"Basic {encoded}"

    def check_account(self, account: KaggleAccount) -> bool:
        if not account.username or not account.key:
            account.reachable = False
            account.error = "credentials_missing"
            account.last_check = time.time()
            return False

        try:
            response = requests.get(
                KAGGLE_API,
                headers={
                    "Authorization": self._auth_header(
                        account.username,
                        account.key,
                    )
                },
                params={
                    "maxSize": 1,
                },
                timeout=20,
            )

            account.last_check = time.time()

            if response.status_code == 200:
                account.reachable = True
                account.error = None
                return True

            if response.status_code in (401, 403):
                account.reachable = False
                account.error = "authentication_failed"
                return False

            if response.status_code == 429:
                account.reachable = False
                account.error = "rate_limited"
                return False

            account.reachable = False
            account.error = f"http_{response.status_code}"
            return False

        except requests.RequestException as exc:
            account.reachable = False
            account.error = type(exc).__name__
            account.last_check = time.time()
            return False

    async def health_check_all(self):
        results = []

        for account in self.accounts:
            # requests is blocking, so run it outside the event loop.
            ok = await asyncio.to_thread(
                self.check_account,
                account,
            )

            results.append({
                "account_id": account.account_id,
                "reachable": ok,
                "last_check": account.last_check,
                "error": account.error,
            })

        return results

    def healthy_accounts(self):
        return [
            account
            for account in self.accounts
            if account.reachable
        ]

    def gpu_candidates(self):
        """
        Returns accounts whose API is currently reachable.

        This does NOT claim that a GPU session is currently available.
        """

        return [
            account.account_id
            for account in self.healthy_accounts()
        ]

    def safe_status(self):
        """
        Never returns usernames or API keys.
        """

        return [
            {
                "account_id": account.account_id,
                "reachable": account.reachable,
                "last_check": account.last_check,
                "error": account.error,
            }
            for account in self.accounts
        ]


async def test():
    adapter = KaggleGPUAdapter()

    print("VIKKY KAGGLE GPU ADAPTER")
    print("Checking Kaggle API connectivity...")

    results = await adapter.health_check_all()

    for result in results:
        print(
            f"{result['account_id']}: "
            f"REACHABLE={result['reachable']} "
            f"ERROR={result['error']}"
        )

    print("\nSAFE STATUS:")
    for item in adapter.safe_status():
        print(item)

    print("\nGPU ACCOUNT API CHECK: COMPLETE")
    print("SECRET EXPOSURE: PROTECTED")
    print("REAL GPU SESSION: NOT CLAIMED")


if __name__ == "__main__":
    asyncio.run(test())

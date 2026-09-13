import os
import sys
import time
import tempfile
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

from uploaders.manager import enabled_providers
from uploaders.adapters import upload_provider


TEST_MB = int(os.getenv("UPLOADER_TEST_MB", "5"))
RETRIES = int(os.getenv("UPLOADER_RETRIES", "3"))

TEST_SIZE = TEST_MB * 1024 * 1024


def make_test_file():
    path = Path(tempfile.gettempdir()) / "vikky_master_uploader_test.bin"

    block = b"VIKKY-MASTER-UPLOADER-TEST\n" * 8192

    with open(path, "wb") as f:
        remaining = TEST_SIZE
        while remaining:
            data = block[:remaining]
            f.write(data)
            remaining -= len(data)

    return path


def valid_url(url):
    return (
        isinstance(url, str)
        and url.strip().startswith(("https://", "http://"))
    )


def get_limit(provider):
    try:
        value = provider.get("max_gb")
        if value is None:
            return None
        return float(value)
    except Exception:
        return None


def size_status(provider):
    limit = get_limit(provider)

    if limit is None:
        return {
            "20": "UNKNOWN",
            "30": "UNKNOWN",
            "40": "UNKNOWN",
            "50": "UNKNOWN",
            "60": "UNKNOWN",
        }

    return {
        "20": "YES" if limit >= 20 else "NO",
        "30": "YES" if limit >= 30 else "NO",
        "40": "YES" if limit >= 40 else "NO",
        "50": "YES" if limit >= 50 else "NO",
        "60": "YES" if limit >= 60 else "NO",
    }


def test_one(provider, test_file):
    name = str(provider.get("name", "")).lower()
    slot = provider.get("slot", 999)

    result = {
        "slot": slot,
        "name": name,
        "status": "FAIL",
        "url": "",
        "attempt": 0,
        "error": "",
        "size": size_status(provider),
    }

    for attempt in range(1, RETRIES + 1):
        result["attempt"] = attempt

        print(
            f"[{name}] attempt "
            f"{attempt}/{RETRIES}"
        )

        try:
            url = upload_provider(
                provider,
                str(test_file)
            )

            if not valid_url(url):
                raise RuntimeError(
                    "Invalid URL returned by provider"
                )

            result["status"] = "PASS"
            result["url"] = url.strip()

            print(
                f"[{name}] PASS "
                f"attempt={attempt}"
            )

            return result

        except Exception as exc:
            result["error"] = str(exc)[:1000]

            print(
                f"[{name}] FAIL "
                f"attempt={attempt}: "
                f"{result['error'][:250]}"
            )

            if attempt < RETRIES:
                time.sleep(2 * attempt)

    return result


def rank(result):
    if result["status"] != "PASS":
        return 999999

    # Lower is better.
    try:
        return int(result["slot"])
    except Exception:
        return 999999


def main():
    print()
    print("=" * 72)
    print("             VIKKY UPLOADER MASTER TEST")
    print("=" * 72)
    print()

    providers = enabled_providers()

    print(
        f"Enabled providers : {len(providers)}"
    )
    print(
        f"Test file         : {TEST_MB} MB"
    )
    print(
        f"Retries/provider  : {RETRIES}"
    )
    print()

    if not providers:
        print("NO ENABLED PROVIDERS")
        return 1

    test_file = make_test_file()

    results = []

    # Test providers together, but limit concurrency.
    workers = min(4, len(providers))

    with ThreadPoolExecutor(
        max_workers=workers
    ) as executor:

        jobs = {
            executor.submit(
                test_one,
                provider,
                test_file,
            ): provider
            for provider in providers
        }

        for future in as_completed(jobs):
            provider = jobs[future]

            try:
                results.append(
                    future.result()
                )
            except Exception as exc:
                results.append({
                    "slot": provider.get("slot", 999),
                    "name": provider.get("name"),
                    "status": "FAIL",
                    "url": "",
                    "attempt": RETRIES,
                    "error": str(exc),
                    "size": size_status(provider),
                })

    results.sort(key=lambda x: int(x["slot"]))

    print()
    print("=" * 72)
    print("                    FINAL MATRIX")
    print("=" * 72)

    for r in results:
        s = r["size"]

        print()
        print(
            f'{int(r["slot"]):02d} | '
            f'{r["name"]:<15} | '
            f'{r["status"]:<6} | '
            f'attempt={r["attempt"]}'
        )

        print(
            f'     20GB={s["20"]} '
            f'30GB={s["30"]} '
            f'40GB={s["40"]} '
            f'50GB={s["50"]} '
            f'60GB={s["60"]}'
        )

        if r["url"]:
            print(
                f'     URL={r["url"]}'
            )

        if r["error"]:
            print(
                f'     ERROR={r["error"][:400]}'
            )

    passed = [
        r for r in results
        if r["status"] == "PASS"
    ]

    failed = [
        r for r in results
        if r["status"] != "PASS"
    ]

    print()
    print("=" * 72)
    print("                    AUTO SELECT")
    print("=" * 72)

    if passed:
        passed.sort(key=rank)

        best = passed[0]

        print()
        print(
            f'BEST PROVIDER : {best["name"]}'
        )
        print(
            f'SLOT          : {best["slot"]}'
        )
        print(
            f'TEST STATUS   : PASS'
        )
        print(
            f'URL           : {best["url"]}'
        )

        print()
        print("FALLBACK ORDER:")

        for i, r in enumerate(passed, 1):
            print(
                f'{i:02d}. {r["name"]}'
            )

    else:
        print()
        print("NO WORKING PROVIDER FOUND.")
        print("Do not upload the production file.")

    print()
    print("=" * 72)
    print("SUMMARY")
    print("=" * 72)
    print(
        f"TOTAL  : {len(results)}"
    )
    print(
        f"PASS   : {len(passed)}"
    )
    print(
        f"FAIL   : {len(failed)}"
    )

    print()
    print(
        "IMPORTANT: PASS means a real test upload "
        "returned a valid URL."
    )
    print(
        "UNKNOWN size means the provider limit "
        "has not yet been configured/verified."
    )
    print()

    try:
        test_file.unlink(missing_ok=True)
    except Exception:
        pass

    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())

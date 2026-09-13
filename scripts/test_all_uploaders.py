import json
import os
import sys
import tempfile
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

from uploaders.manager import enabled_providers
from uploaders.adapters import upload_provider, UploadError


TEST_SIZE_MB = int(os.getenv("UPLOADER_TEST_SIZE_MB", "5"))
TEST_SIZE = TEST_SIZE_MB * 1024 * 1024

SIZE_TIERS_GB = [20, 30, 40, 50, 60]


def make_test_file():
    path = Path(tempfile.gettempdir()) / "vikky_uploader_batch_test.bin"

    chunk = b"VIKKY-UPLOADER-BATCH-TEST\n" * 4096
    remaining = TEST_SIZE

    with path.open("wb") as f:
        while remaining > 0:
            data = chunk[:remaining]
            f.write(data)
            remaining -= len(data)

    return path


def get_limit(provider):
    value = provider.get("max_gb")

    if value is None:
        return None

    try:
        return float(value)
    except Exception:
        return None


def size_matrix(provider):
    limit = get_limit(provider)

    result = {}

    for gb in SIZE_TIERS_GB:
        if limit is None:
            result[gb] = "UNKNOWN"
        elif limit >= gb:
            result[gb] = "YES"
        else:
            result[gb] = "NO"

    return result


def test_provider(provider, test_file):
    name = str(provider.get("name", "")).lower()

    result = {
        "slot": provider.get("slot"),
        "name": name,
        "adapter": "UNKNOWN",
        "auth": "UNKNOWN",
        "real_upload": "NOT_TESTED",
        "url": "",
        "error": "",
        "size_matrix": size_matrix(provider),
    }

    token_env = provider.get("token_env")

    if token_env:
        result["auth"] = (
            "CONFIGURED"
            if os.getenv(token_env)
            else "MISSING"
        )
    else:
        result["auth"] = "NOT_REQUIRED/UNKNOWN"

    try:
        # Adapter availability check
        if name not in {
            "buzzheavier",
            "gofile",
            "0807",
            "storage_to",
            "pixeldrain",
        }:
            result["adapter"] = "NOT_IMPLEMENTED"
            result["real_upload"] = "SKIPPED"
            return result

        result["adapter"] = "IMPLEMENTED"

        print(
            f"[{name}] REAL UPLOAD START "
            f"({TEST_SIZE_MB} MB)"
        )

        url = upload_provider(provider, str(test_file))

        if not isinstance(url, str):
            raise UploadError("Provider returned non-string URL")

        url = url.strip()

        if not url.startswith(("https://", "http://")):
            raise UploadError(
                "Provider returned invalid download URL"
            )

        result["real_upload"] = "PASS"
        result["url"] = url

        print(f"[{name}] REAL UPLOAD PASS")

    except Exception as exc:
        message = str(exc).strip()

        result["real_upload"] = "FAIL"
        result["error"] = message[:1000]

        print(
            f"[{name}] REAL UPLOAD FAIL: "
            f"{message[:300]}"
        )

    return result


def main():
    print()
    print("=" * 70)
    print("          VIKKY ENCODER - ALL UPLOADER TEST")
    print("=" * 70)
    print()

    providers = enabled_providers()

    print(f"ENABLED PROVIDERS: {len(providers)}")
    print(f"REAL TEST SIZE:    {TEST_SIZE_MB} MB")
    print()

    if not providers:
        print("NO ENABLED PROVIDERS")
        return 1

    test_file = make_test_file()

    print(f"TEST FILE: {test_file}")
    print()

    results = []

    # Batch execution.
    # max_workers prevents unlimited simultaneous uploads.
    workers = min(4, len(providers))

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(
                test_provider,
                provider,
                test_file,
            ): provider
            for provider in providers
        }

        for future in as_completed(futures):
            provider = futures[future]

            try:
                results.append(future.result())
            except Exception as exc:
                results.append({
                    "slot": provider.get("slot"),
                    "name": provider.get("name"),
                    "adapter": "ERROR",
                    "auth": "UNKNOWN",
                    "real_upload": "FAIL",
                    "url": "",
                    "error": str(exc),
                    "size_matrix": size_matrix(provider),
                })

    results.sort(key=lambda x: int(x.get("slot", 999)))

    print()
    print("=" * 70)
    print("RESULT MATRIX")
    print("=" * 70)

    for r in results:
        matrix = r["size_matrix"]

        print()
        print(
            f'{int(r["slot"]):02d} | '
            f'{r["name"]:<15} | '
            f'ADAPTER={r["adapter"]:<15} | '
            f'AUTH={r["auth"]:<18} | '
            f'UPLOAD={r["real_upload"]}'
        )

        print(
            "     SIZE: "
            f'20GB={matrix[20]} | '
            f'30GB={matrix[30]} | '
            f'40GB={matrix[40]} | '
            f'50GB={matrix[50]} | '
            f'60GB={matrix[60]}'
        )

        if r["url"]:
            print(f'     URL: {r["url"]}')

        if r["error"]:
            print(f'     ERROR: {r["error"][:500]}')

    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)

    adapter_ok = sum(
        r["adapter"] == "IMPLEMENTED"
        for r in results
    )

    upload_ok = sum(
        r["real_upload"] == "PASS"
        for r in results
    )

    upload_fail = sum(
        r["real_upload"] == "FAIL"
        for r in results
    )

    not_impl = sum(
        r["adapter"] == "NOT_IMPLEMENTED"
        for r in results
    )

    print(f"TOTAL ENABLED : {len(results)}")
    print(f"ADAPTER READY : {adapter_ok}")
    print(f"UPLOAD PASS   : {upload_ok}")
    print(f"UPLOAD FAIL   : {upload_fail}")
    print(f"NOT IMPLEMENT : {not_impl}")

    print()
    print("IMPORTANT:")
    print("PASS = real test-file upload + valid URL.")
    print("20/30/40/50/60GB = configured capability matrix.")
    print("It does NOT upload a 60GB test file.")
    print()

    try:
        test_file.unlink(missing_ok=True)
    except Exception:
        pass

    # Exit non-zero only when an enabled provider that has
    # an implemented adapter failed its real upload.
    if upload_fail:
        return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from pathlib import Path

from app.workers.kaggle_ai_worker import create_worker


test_file = Path("temp/worker_test.mkv")
test_file.parent.mkdir(parents=True, exist_ok=True)
test_file.write_bytes(b"VIKKY_WORKER_TEST")

worker = create_worker("kaggle-1")

job = worker.build_job(
    input_file=test_file,
    output_file="outputs/test_4k.mkv",
    mode="4K_AI",
)

print("KAGGLE AI WORKER READY")
print("Worker:", job["worker_id"])
print("Engine:", job["engine"])
print("Execution:", job["execution"])
print("Mode:", job["mode"])
print("Audio:", job["audio"])

test_file.unlink(missing_ok=True)

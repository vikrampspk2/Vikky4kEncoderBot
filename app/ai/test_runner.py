from pathlib import Path
from app.ai.engines.runner import AIWorkerRunner

test_input = Path("temp/ai_test_input.mkv")
test_input.parent.mkdir(parents=True, exist_ok=True)
test_input.write_bytes(b"VIKKY_TEST")

runner = AIWorkerRunner()

result = runner.prepare(
    input_path=str(test_input),
    output_path="outputs/ai_test_output.mkv",
    source_class="full_hd",
    mode="4K_AI",
)

print("AI WORKER CONTRACT OK")
print("Engine:", result["engine"])
print("Mode:", result["mode"])
print("Status:", result["status"])

test_input.unlink(missing_ok=True)

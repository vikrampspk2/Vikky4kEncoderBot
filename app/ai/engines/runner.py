from pathlib import Path
from app.ai.router import get_ai_engine


class AIWorkerRunner:

    def __init__(self):
        self.engine = None

    def prepare(self, input_path, output_path, source_class, mode):
        input_file = Path(input_path)
        output_file = Path(output_path)

        if not input_file.exists():
            raise FileNotFoundError(f"Input not found: {input_file}")

        if input_file.stat().st_size == 0:
            raise ValueError("Input file is empty")

        self.engine = get_ai_engine(source_class, mode)

        if self.engine is None:
            raise ValueError(f"No AI engine available for mode: {mode}")

        output_file.parent.mkdir(parents=True, exist_ok=True)

        return {
            "engine": self.engine.name(),
            "mode": mode,
            "input": str(input_file),
            "output": str(output_file),
            "status": "READY_FOR_GPU",
        }

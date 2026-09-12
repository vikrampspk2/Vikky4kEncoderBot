from pathlib import Path
from config.settings import (
    KAGGLE1_USERNAME,
    KAGGLE1_KEY,
    KAGGLE2_USERNAME,
    KAGGLE2_KEY,
)

BASE_DIR = Path(__file__).resolve().parents[2]

WORKERS = [
    {
        "id": "kaggle-1",
        "username": KAGGLE1_USERNAME,
        "key": KAGGLE1_KEY,
    },
    {
        "id": "kaggle-2",
        "username": KAGGLE2_USERNAME,
        "key": KAGGLE2_KEY,
    },
]

TEMP_DIR = BASE_DIR / "temp"
OUTPUT_DIR = BASE_DIR / "outputs"
MODEL_DIR = BASE_DIR / "models"
LOG_DIR = BASE_DIR / "logs"

for directory in (TEMP_DIR, OUTPUT_DIR, MODEL_DIR, LOG_DIR):
    directory.mkdir(parents=True, exist_ok=True)

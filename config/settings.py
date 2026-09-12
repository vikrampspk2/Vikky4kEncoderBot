import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

AI_API_KEY = os.getenv("AI_API_KEY", "").strip()

OWNER_IDS = [
    int(x.strip())
    for x in os.getenv("OWNER_IDS", "").split(",")
    if x.strip().isdigit()
]

KAGGLE1_USERNAME = os.getenv("KAGGLE1_USERNAME", "").strip()
KAGGLE1_KEY = os.getenv("KAGGLE1_KEY", "").strip()

KAGGLE2_USERNAME = os.getenv("KAGGLE2_USERNAME", "").strip()
KAGGLE2_KEY = os.getenv("KAGGLE2_KEY", "").strip()

APP_NAME = "VIKKY Encoder"

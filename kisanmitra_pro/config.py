import os
from dotenv import load_dotenv

load_dotenv()

# === API KEYS ===
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")

# === GROQ MODELS ===
GROQ_CHAT_MODEL = "llama-3.3-70b-versatile"
GROQ_VISION_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"
GROQ_WHISPER_MODEL = "whisper-large-v3"

# === DEFAULT LOCATION (Latur, Maharashtra) ===
DEFAULT_LAT = 18.4088
DEFAULT_LON = 76.5604
DEFAULT_LOCATION = "Latur, Maharashtra"

# === DATABASE ===
DATABASE_URL = os.environ.get("DATABASE_URL", "")
IS_POSTGRES = DATABASE_URL.startswith("postgres")
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "kisanmitra.db")

# === GOVT API ===
MANDI_API_KEY = os.environ.get("MANDI_API_KEY", "")

# === APP SETTINGS ===
MAX_HISTORY = 8
MORNING_ALERT_HOUR = 7
VERSION = "2.0.0"

# === DASHBOARD AUTH ===
GOOGLE_CLIENT_ID     = os.environ.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
FLASK_SECRET_KEY     = os.environ.get("FLASK_SECRET_KEY", "kisanmitra-change-in-prod")
DASHBOARD_PORT       = int(os.environ.get("PORT", 8080))

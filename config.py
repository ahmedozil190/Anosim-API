import os
from dotenv import load_dotenv

load_dotenv()

# Anosim API Settings
ANOSIM_API_KEY = os.getenv("ANOSIM_API_KEY", "YOUR_API_KEY_HERE")
ANOSIM_BASE_URL = "https://anosim.net/api/v1"

# Telegram API Settings (from my.telegram.org)
TELEGRAM_API_ID = int(os.getenv("TELEGRAM_API_ID", 0))
TELEGRAM_API_HASH = os.getenv("TELEGRAM_API_HASH", "")

# Management Bot Token
BOT_TOKEN = os.getenv("BOT_TOKEN", "")

# Database Settings
DB_PATH = "database.db"

# Storage
SESSIONS_DIR = "sessions"
if not os.path.exists(SESSIONS_DIR):
    os.makedirs(SESSIONS_DIR)

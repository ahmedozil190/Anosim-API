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

# Proxy for Telethon (SOCKS5) — required for 'SMS fee' bypass
# Set PROXY_HOST in your .env to enable. Leave empty to disable.
PROXY_HOST = os.getenv("PROXY_HOST", "")  # e.g. 1.2.3.4
PROXY_PORT = int(os.getenv("PROXY_PORT", "1080"))
PROXY_USER = os.getenv("PROXY_USER", "")
PROXY_PASS = os.getenv("PROXY_PASS", "")

# Persistent Storage: use /data if it exists (hosting Volume), else use local directory
_DATA_DIR = "/data" if os.path.isdir("/data") else os.path.dirname(os.path.abspath(__file__))

# Database
DB_PATH = os.path.join(_DATA_DIR, "database.db")

# Sessions
SESSIONS_DIR = os.path.join(_DATA_DIR, "sessions")
os.makedirs(SESSIONS_DIR, exist_ok=True)

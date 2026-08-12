import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()


def _resolve_db_path() -> str:
    """
    مسیر پایدار برای دیتابیس:
    1) متغیر DB_PATH اگر ست شده باشد
    2) اگر پوشه /data وجود داشته باشد (دیسک پایدار Render/Railway) → /data/bot_data.db
    3) در غیر این صورت DATA_DIR یا پوشه data کنار پروژه
    """
    env_path = os.getenv("DB_PATH")
    if env_path:
        return env_path

    # دیسک پایدار رایج روی Render / Fly / Railway
    if Path("/data").is_dir() and os.access("/data", os.W_OK):
        return "/data/bot_data.db"

    data_dir = os.getenv("DATA_DIR", "data")
    Path(data_dir).mkdir(parents=True, exist_ok=True)
    return str(Path(data_dir) / "bot_data.db")


class Config:
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN is required!")

    ADMIN_IDS = [int(id.strip()) for id in os.getenv("ADMIN_IDS", "").split(",") if id.strip()]

    REQUIRED_CHANNEL_ID = int(os.getenv("CHANNEL_ID", "-1004385593103"))
    REQUIRED_CHANNEL_LINK = os.getenv("CHANNEL_LINK", "https://t.me/HmHermi")

    # مسیر دیتابیس پایدار
    DB_PATH = _resolve_db_path()
    # پوشه بکاپ (همان دیسک پایدار)
    BACKUP_DIR = os.getenv(
        "BACKUP_DIR",
        str(Path(DB_PATH).parent / "backups"),
    )

    TIMEZONE = os.getenv("TIMEZONE", "Asia/Tehran")
    PRAYER_METHOD = int(os.getenv("PRAYER_METHOD", "7"))
    CACHE_TTL = int(os.getenv("CACHE_TTL", "300"))
    RATE_LIMIT = int(os.getenv("RATE_LIMIT", "300"))
    START_RATE_LIMIT = int(os.getenv("START_RATE_LIMIT", "10"))
    GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "")
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

    # تعداد بکاپ‌هایی که نگه داشته می‌شوند
    BACKUP_KEEP = int(os.getenv("BACKUP_KEEP", "14"))

    # DeepSeek AI
    DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
    DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")
    AI_MAX_INPUT = int(os.getenv("AI_MAX_INPUT", "5000"))
    AI_MAX_OUTPUT = int(os.getenv("AI_MAX_OUTPUT", "1500"))
    AI_HISTORY_ITEMS = int(os.getenv("AI_HISTORY_ITEMS", "8"))


config = Config()

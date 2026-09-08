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
    HTTP_TIMEOUT = float(os.getenv("HTTP_TIMEOUT", "15"))
    HTTP_RETRIES = int(os.getenv("HTTP_RETRIES", "2"))
    HTTP_GET_CACHE_TTL = float(os.getenv("HTTP_GET_CACHE_TTL", "12"))
    AI_TOOL_TIMEOUT = float(os.getenv("AI_TOOL_TIMEOUT", "25"))
    AI_TOOL_CONCURRENCY = int(os.getenv("AI_TOOL_CONCURRENCY", "8"))
    RATE_LIMIT = int(os.getenv("RATE_LIMIT", "300"))
    START_RATE_LIMIT = int(os.getenv("START_RATE_LIMIT", "10"))
    GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "")
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    METRICS_TOKEN = os.getenv("METRICS_TOKEN", "").strip()
    RESTORE_MAX_BYTES = int(os.getenv("RESTORE_MAX_BYTES", str(256 * 1024 * 1024)))

    # تعداد بکاپ‌هایی که نگه داشته می‌شوند
    BACKUP_KEEP = int(os.getenv("BACKUP_KEEP", "14"))
    AUTOMATION_DIGEST_HOUR = int(os.getenv("AUTOMATION_DIGEST_HOUR", "8"))
    # Deployment/runtime diagnostics (safe to expose only as non-secret metadata).
    RELEASE_VERSION = os.getenv("RELEASE_VERSION", "").strip()
    DEPLOYMENT_ID = os.getenv("DEPLOYMENT_ID", os.getenv("RENDER_GIT_COMMIT", "")).strip()
    STARTUP_CHECK = os.getenv("STARTUP_CHECK", "true").strip().lower() not in {"0", "false", "no", "off"}


config = Config()


# V28: bounded AI tool cache
AI_TOOL_CACHE_MAX = max(64, int(os.getenv("AI_TOOL_CACHE_MAX", "1024")))

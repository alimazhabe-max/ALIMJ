import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # توکن ربات
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN is required!")

    # لیست ادمین‌ها (آیدی عددی)
    ADMIN_IDS = [int(id.strip()) for id in os.getenv("ADMIN_IDS", "").split(",") if id.strip()]

    # اطلاعات کانال اجباری
    REQUIRED_CHANNEL_ID = int(os.getenv("CHANNEL_ID", "-1004385593103"))
    REQUIRED_CHANNEL_LINK = os.getenv("CHANNEL_LINK", "https://t.me/HmHermi")

    # تنظیمات دیتابیس
    DB_PATH = os.getenv("DB_PATH", "bot_data.db")

    # منطقه زمانی
    TIMEZONE = os.getenv("TIMEZONE", "Asia/Tehran")

    # روش محاسبه اوقات شرعی (7 = مؤسسه استاندارد مصر)
    PRAYER_METHOD = int(os.getenv("PRAYER_METHOD", "7"))

    # کش API (بر حسب ثانیه)
    CACHE_TTL = int(os.getenv("CACHE_TTL", "300"))  # 5 دقیقه

    # محدودیت درخواست (تعداد در دقیقه)
    RATE_LIMIT = int(os.getenv("RATE_LIMIT", "300"))
    START_RATE_LIMIT = int(os.getenv("START_RATE_LIMIT", "10"))

    # کلید Google Maps (اختیاری — برای فاصله جهانی دقیق‌تر)
    GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "")

    # سطح لاگ
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

config = Config()

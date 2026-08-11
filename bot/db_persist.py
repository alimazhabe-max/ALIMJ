# -*- coding: utf-8 -*-
"""
بکاپ و ریستور رایگان از طریق تلگرام (بدون نیاز به دیسک پولی)
"""
import asyncio
from pathlib import Path
from datetime import datetime

from bot.config import config
from bot.database import DB_PATH, backup_db, _user_count, get_db_connection
from bot.logger import logger


async def send_db_to_admins(bot, caption: str = None):
    """ارسال فایل دیتابیس برای همه ادمین‌ها"""
    path = Path(DB_PATH)
    if not path.exists():
        return False, "فایل دیتابیس وجود ندارد"

    # اول بکاپ محلی
    try:
        backup_db()
    except Exception:
        pass

    users = _user_count(DB_PATH)
    size_kb = path.stat().st_size / 1024
    cap = caption or (
        f"💾 بکاپ دیتابیس ربات\n"
        f"👥 کاربران: {users}\n"
        f"📦 حجم: {size_kb:.1f} KB\n"
        f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
        f"برای بازگردانی بعد از دیپلوی:\n"
        f"همین فایل را برای ربات بفرست و کپشن بگذار: /restore"
    )

    ok = 0
    for admin_id in config.ADMIN_IDS:
        try:
            with open(path, "rb") as f:
                await bot.send_document(
                    chat_id=admin_id,
                    document=f,
                    filename=f"bot_backup_{datetime.now().strftime('%Y%m%d_%H%M')}.db",
                    caption=cap,
                )
            ok += 1
            await asyncio.sleep(0.3)
        except Exception as e:
            logger.error(f"Send backup to admin {admin_id} failed: {e}")
    return ok > 0, f"ارسال به {ok}/{len(config.ADMIN_IDS)} ادمین (کاربران: {users})"


async def restore_db_from_file(file_path: str) -> tuple[bool, str]:
    """جایگزینی دیتابیس با فایل آپلودشده"""
    src = Path(file_path)
    if not src.exists() or src.stat().st_size < 100:
        return False, "فایل نامعتبر است"

    n = _user_count(src)
    if n == 0:
        # ممکن است ساختار فرق کند؛ باز هم اجازه بده ولی هشدار بده
        logger.warning("Restore file has 0 users (or unreadable)")

    # بکاپ از وضعیت فعلی قبل از جایگزین
    try:
        if Path(DB_PATH).exists() and _user_count(DB_PATH) > 0:
            backup_db()
    except Exception:
        pass

    dest = Path(DB_PATH)
    dest.parent.mkdir(parents=True, exist_ok=True)
    # کپی با نام موقت بعد جابه‌جایی
    tmp = dest.with_suffix(".db.restoring")
    import shutil
    shutil.copy2(src, tmp)
    tmp.replace(dest)

    # تست باز شدن
    try:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM users")
        final = c.fetchone()[0]
        conn.close()
    except Exception as e:
        return False, f"فایل دیتابیس معتبر نیست: {e}"

    return True, f"✅ بازگردانی موفق — {final} کاربر"


async def notify_admins_if_empty(bot):
    """اگر بعد از دیپلوی دیتابیس خالی بود، به ادمین خبر بده"""
    n = _user_count(DB_PATH)
    if n > 0:
        return
    if not config.ADMIN_IDS:
        return
    text = (
        "⚠️ دیتابیس ربات خالی است (احتمالاً بعد از دیپلوی جدید).\n\n"
        "اگر بکاپ داری:\n"
        "۱) فایل .db بکاپ را برای ربات بفرست\n"
        "۲) کپشن پیام را بگذار: /restore\n\n"
        "یا از دکمه/دستور /backup روی نسخه قبلی استفاده کن."
    )
    for admin_id in config.ADMIN_IDS:
        try:
            await bot.send_message(chat_id=admin_id, text=text)
            await asyncio.sleep(0.2)
        except Exception as e:
            logger.error(f"notify empty db: {e}")

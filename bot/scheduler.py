from datetime import time, datetime
import pytz
from bot.logger import logger
from bot.database import get_all_users, update_stats, get_users_for_azan, backup_db
from bot.utils.helpers import build_message, get_refresh_button
from bot.config import config
from bot.api.prayer import get_prayer_times
from bot.db_persist import send_db_to_admins
import asyncio

PRAYER_FLAGS = {
    "اذان صبح": 3,
    "اذان ظهر": 4,
    "اذان عصر": 5,
    "اذان مغرب": 6,
    "اذان عشاء": 7,
}


async def send_daily_messages(context):
    logger.info("Starting daily broadcast...")
    users = get_all_users()
    count = 0
    for user_id, first_name, city, lang in users:
        try:
            msg = await build_message(user_id, first_name, city)
            await context.bot.send_message(
                chat_id=user_id,
                text=msg,
                reply_markup=get_refresh_button()
            )
            count += 1
            await asyncio.sleep(0.2)
        except Exception as e:
            logger.error(f"Failed to send to {user_id}: {e}")
    logger.info(f"Daily broadcast sent to {count}/{len(users)} users")


async def check_azan_notifications(context):
    tehran = pytz.timezone(config.TIMEZONE)
    now = datetime.now(tehran)
    users = get_users_for_azan()
    for row in users:
        try:
            user_id = row[0]
            city = row[1] if len(row) > 1 and row[1] else "تهران"
            times = get_prayer_times(city) or {}
            for prayer_name, flag_idx in PRAYER_FLAGS.items():
                if flag_idx >= len(row) or not row[flag_idx]:
                    continue
                tstr = times.get(prayer_name)
                if not tstr:
                    continue
                try:
                    hh, mm = map(int, tstr.split(":")[:2])
                except Exception:
                    continue
                target = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
                diff = (target - now).total_seconds()
                if 0 <= diff < 60:
                    text = (
                        f"🔔 {prayer_name}\n"
                        f"شهر: {city}\n"
                        f"ساعت: {tstr}\n\n"
                        f"الله اکبر"
                    )
                    await context.bot.send_message(chat_id=user_id, text=text)
                    await asyncio.sleep(0.05)
        except Exception as e:
            logger.error(f"azan notify error: {e}")


async def periodic_backup(context):
    """بکاپ خودکار: GitHub (اگر ست شده) + تلگرام ادمین"""
    try:
        from bot.db_persist import auto_backup, send_db_to_admins, github_enabled
        ok, msg = auto_backup()
        logger.info(f"auto_backup: {msg}")
        # اگر GitHub نبود، به تلگرام هم بفرست
        if not github_enabled():
            ok2, msg2 = await send_db_to_admins(context.bot)
            logger.info(f"telegram backup: {msg2}")
    except Exception as e:
        logger.error(f"periodic backup error: {e}")


def setup_scheduler(app):
    job_queue = app.job_queue
    if not job_queue:
        logger.error("JobQueue not available! Scheduler disabled.")
        return

    tehran = pytz.timezone(config.TIMEZONE)

    job_queue.run_daily(
        send_daily_messages,
        time=time(hour=0, minute=0, second=0, tzinfo=tehran),
        name="daily_broadcast",
    )
    job_queue.run_daily(
        lambda ctx: update_stats(),
        time=time(hour=23, minute=59, second=0, tzinfo=tehran),
        name="daily_stats",
    )
    job_queue.run_repeating(
        check_azan_notifications,
        interval=60,
        first=10,
        name="azan_timer",
    )
    # هر ۱۲ ساعت بکاپ به تلگرام ادمین
    job_queue.run_repeating(
        periodic_backup,
        interval=12 * 3600,
        first=300,
        name="db_backup_telegram",
    )
    logger.info("Scheduler ready: daily + azan + telegram backup every 12h")

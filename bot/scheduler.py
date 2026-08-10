from datetime import time, datetime
import pytz
from bot.logger import logger
from bot.database import get_all_users, update_stats
from bot.utils.helpers import build_message, get_refresh_button
from bot.config import config
from bot.api.prayer import get_prayer_times
import asyncio

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
    """هر دقیقه: نزدیک اذان صبح/مغرب اطلاع بده"""
    tehran = pytz.timezone(config.TIMEZONE)
    now = datetime.now(tehran)
    users = get_all_users()
    for row in users:
        try:
            user_id = row[0]
            city = row[2] if len(row) > 2 else "تهران"
            times = get_prayer_times(city) or {}
            for key in ("اذان صبح", "اذان مغرب"):
                tstr = times.get(key)
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
                        f"🔔 {key}\n"
                        f"شهر: {city}\n"
                        f"ساعت: {tstr}\n\n"
                        f"الله اکبر"
                    ).replace("\\n", "\n")
                    # real newlines:
                    text = f"🔔 {key}\nشهر: {city}\nساعت: {tstr}\n\nالله اکبر"
                    text = text.encode().decode("unicode_escape") if False else (
                        "🔔 " + key + "\nشهر: " + str(city) + "\nساعت: " + str(tstr) + "\n\nالله اکبر"
                    )
                    text = "🔔 " + str(key) + "\n" + "شهر: " + str(city) + "\n" + "ساعت: " + str(tstr) + "\n\nالله اکبر"
                    # simplest:
                    text = "🔔 %s\nشهر: %s\nساعت: %s\n\nالله اکبر" % (key, city, tstr)
                    text = text.replace("\n", "\n")
                    await context.bot.send_message(chat_id=user_id, text="🔔 " + key + chr(10) + "شهر: " + str(city) + chr(10) + "ساعت: " + str(tstr) + chr(10)+chr(10) + "الله اکبر")
                    await asyncio.sleep(0.05)
        except Exception as e:
            logger.error(f"azan notify error: {e}")


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
    logger.info("Scheduler ready: daily + azan timer")

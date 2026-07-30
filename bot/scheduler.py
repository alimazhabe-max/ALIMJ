from datetime import time
import pytz
from bot.logger import logger
from bot.database import get_all_users, update_stats
from bot.utils.helpers import build_message
from bot.config import config
import asyncio

async def send_daily_messages(context):
    logger.info("Starting daily broadcast...")
    users = get_all_users()
    count = 0
    for user_id, first_name, city, lang in users:
        try:
            msg = build_message(user_id, first_name, city)
            await context.bot.send_message(chat_id=user_id, text=msg)
            count += 1
            await asyncio.sleep(0.2)
        except Exception as e:
            logger.error(f"Failed to send to {user_id}: {e}")
    logger.info(f"Daily broadcast sent to {count}/{len(users)} users")

def setup_scheduler(app):
    job_queue = app.job_queue
    if not job_queue:
        logger.error("JobQueue not available! Scheduler disabled.")
        return

    tehran = pytz.timezone(config.TIMEZONE)

    # ارسال روزانه ساعت ۰۰:۰۰ به وقت تهران
    job_queue.run_daily(
        send_daily_messages,
        time=time(hour=0, minute=0, second=0, tzinfo=tehran),
        name="daily_broadcast"
    )
    logger.info("Daily broadcast scheduled at 00:00 Tehran time")

    # به‌روزرسانی آمار روزانه ساعت ۲۳:۵۹
    job_queue.run_daily(
        lambda ctx: update_stats(),
        time=time(hour=23, minute=59, second=0, tzinfo=tehran),
        name="daily_stats"
    )
    logger.info("Stats update scheduled at 23:59 Tehran time")

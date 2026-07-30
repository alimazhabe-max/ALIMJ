from apscheduler.triggers.cron import CronTrigger
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
            await asyncio.sleep(0.2)   # همین خط اشکال ندارد
        except Exception as e:
            logger.error(f"Failed to send to {user_id}: {e}")
    logger.info(f"Daily broadcast sent to {count}/{len(users)} users")

def setup_scheduler(app):
    job_queue = app.job_queue
    if not job_queue:
        logger.error("JobQueue not available! Scheduler disabled.")
        return

    # ارسال روزانه ساعت ۰۰:۰۰ به وقت تهران
    trigger = CronTrigger(hour=0, minute=0, second=0, timezone=config.TIMEZONE)
    job_queue.run_custom(send_daily_messages, trigger=trigger, name="daily_broadcast")
    logger.info("Daily broadcast scheduled at 00:00 Tehran time")

    # به‌روزرسانی آمار روزانه ساعت ۲۳:۵۹
    stats_trigger = CronTrigger(hour=23, minute=59, timezone=config.TIMEZONE)
    job_queue.run_custom(lambda ctx: update_stats(), trigger=stats_trigger, name="daily_stats")
    logger.info("Stats update scheduled at 23:59 Tehran time")

from datetime import time, datetime, timedelta
import pytz
from bot.logger import logger
from bot.database import (
    get_all_users,
    update_stats,
    get_users_for_azan,
    backup_db,
    get_pending_reminders,
    mark_reminder_done,
    reschedule_reminder,
)
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


def _next_occurrence(when: datetime, repeat_type: str, repeat_every: int) -> datetime | None:
    """محاسبه زمان بعدی برای یادآوری تکراری."""
    rt = (repeat_type or "once").lower()
    if rt in ("once", "", "none"):
        return None
    if rt == "daily":
        return when + timedelta(days=max(1, repeat_every or 1))
    if rt == "weekly":
        return when + timedelta(weeks=max(1, repeat_every or 1))
    if rt == "monthly":
        # تقریبی ۳۰ روز
        return when + timedelta(days=30 * max(1, repeat_every or 1))
    if rt in ("every_minutes", "minutes", "minutely"):
        mins = max(1, int(repeat_every or 1))
        return when + timedelta(minutes=mins)
    if rt in ("every_hours", "hours", "hourly"):
        hrs = max(1, int(repeat_every or 1))
        return when + timedelta(hours=hrs)
    return None


async def check_user_reminders(context):
    """ارسال یادآوری‌های سررسید (یک‌بار و تکراری)."""
    tehran = pytz.timezone(config.TIMEZONE)
    now = datetime.now(tehran)
    now_iso = now.isoformat()
    try:
        rows = get_pending_reminders(before_time=now_iso)
    except Exception as e:
        logger.error(f"get_pending_reminders: {e}")
        return

    for row in rows:
        try:
            if len(row) >= 7:
                rid, user_id, text, remind_at, repeat_type, repeat_every, active = row[:7]
            else:
                rid, user_id, text, remind_at = row[:4]
                repeat_type, repeat_every, active = "once", 0, 1

            if not active:
                continue

            body = text or "یادآوری"
            msg = f"⏰ یادآوری\n\n{body}"
            if repeat_type and repeat_type not in ("once", "", "none"):
                msg += f"\n\n🔁 تکرار: {repeat_type}"
                if repeat_every:
                    msg += f" (هر {repeat_every})"

            await context.bot.send_message(chat_id=user_id, text=msg)

            # زمان پایه برای محاسبه بعدی
            try:
                base = datetime.fromisoformat(remind_at)
                if base.tzinfo is None:
                    base = tehran.localize(base)
            except Exception:
                base = now

            nxt = _next_occurrence(base, repeat_type, int(repeat_every or 0))
            # اگر از الان عقب‌تر شد، از الان جلو برو
            if nxt is not None:
                while nxt <= now:
                    nxt2 = _next_occurrence(nxt, repeat_type, int(repeat_every or 0))
                    if nxt2 is None or nxt2 <= nxt:
                        break
                    nxt = nxt2
                reschedule_reminder(rid, nxt.isoformat())
            else:
                mark_reminder_done(rid)

            await asyncio.sleep(0.05)
        except Exception as e:
            logger.error(f"reminder send error: {e}")


async def periodic_backup(context):
    """بکاپ خودکار: GitHub (اگر ست شده) + تلگرام ادمین"""
    try:
        from bot.db_persist import auto_backup, send_db_to_admins, github_enabled
        ok, msg = auto_backup()
        logger.info(f"auto_backup: {msg}")
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
    # یادآوری‌های کاربر هر ۳۰ ثانیه
    job_queue.run_repeating(
        check_user_reminders,
        interval=30,
        first=15,
        name="user_reminders",
    )
    job_queue.run_repeating(
        periodic_backup,
        interval=12 * 3600,
        first=300,
        name="db_backup_telegram",
    )
    logger.info("Scheduler ready: daily + azan + reminders + telegram backup every 12h")

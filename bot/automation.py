"""Opt-in proactive assistant automation.

The digest is deliberately conservative: no unsolicited messages unless the
user enables it, and at most one digest per user per local day.
"""
from datetime import datetime
import pytz

from bot.config import config
from bot.database import (
    get_users_for_daily_digest,
    mark_daily_digest_sent,
    get_upcoming_user_reminders,
    get_top_user_features,
    get_user_city,
)
from bot.logger import logger


def build_daily_digest(user_id, now=None):
    tz = pytz.timezone(config.TIMEZONE)
    now = now or datetime.now(tz)
    lines = ["🌅 خلاصه شخصی امروز", ""]

    reminders = get_upcoming_user_reminders(user_id, now.isoformat(), 4)
    if reminders:
        lines.append("⏰ یادآوری‌های پیش رو:")
        for text, remind_at, repeat_type in reminders:
            try:
                dt = datetime.fromisoformat(remind_at)
                if dt.tzinfo is None:
                    dt = tz.localize(dt)
                when = dt.astimezone(tz).strftime("%H:%M")
            except Exception:
                when = "--:--"
            repeat = " 🔁" if repeat_type not in ("once", "", "none") else ""
            lines.append(f"• {when} — {(text or 'یادآوری')[:100]}{repeat}")
        lines.append("")

    city = get_user_city(user_id)
    if city:
        lines.append(f"📍 شهر پیش‌فرض: {city}")

    top = get_top_user_features(user_id, 2)
    if top:
        labels = {"market": "بازار", "forecast": "پیش‌بینی هوا", "aqi": "کیفیت هوا", "location": "مکان", "weather": "هوا"}
        names = [labels.get(name, name) for name, _ in top]
        lines.append("⭐ پرکاربرد اخیر: " + "، ".join(names))

    if not reminders and not city and not top:
        lines.append("امروز چیزی برای یادآوری یا پیشنهاد شخصی نداریم. روز خوبی داشته باشی! ☀️")
    else:
        lines.append("\nهر وقت بخواهی، من اینجا هستم. 🤖")
    return "\n".join(lines)


async def send_daily_digests(context):
    tz = pytz.timezone(config.TIMEZONE)
    now = datetime.now(tz)
    date_key = now.strftime("%Y-%m-%d")
    users = get_users_for_daily_digest(date_key)
    sent = 0
    for (user_id,) in users:
        try:
            # Atomic DB claim prevents duplicate sends if scheduler overlaps.
            if not mark_daily_digest_sent(user_id, date_key):
                continue
            await context.bot.send_message(chat_id=user_id, text=build_daily_digest(user_id, now))
            sent += 1
        except Exception as exc:
            logger.warning("daily digest failed for %s: %s", user_id, exc)
    logger.info("Daily proactive digest sent to %s/%s users", sent, len(users))

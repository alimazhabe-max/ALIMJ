"""Domain-specific Telegram handlers. Compatibility-preserving extraction from feature_handlers."""
from __future__ import annotations
from bot.database import set_birth_date
from bot.utils.helpers import get_date_tools_keyboard
from bot.features.date.date_tools import parse_shamsi, parse_any_date, parse_two_dates, parse_countdown, birthday_countdown, zodiac_animal, lunar_age, date_diff, age_diff, convert_with_weekday, search_events, custom_countdown
from bot.features.date.converters import calculate_age, parse_birth_datetime

async def _h_date_convert(u, c, t, uid):
    c.user_data.pop("waiting_for", None)
    p = parse_any_date(t)
    await u.message.reply_text(convert_with_weekday(*p) if p else "❌ نامعتبر", reply_markup=get_date_tools_keyboard())

async def _h_age_calc(u, c, t, uid):
    c.user_data.pop("waiting_for", None)
    p = parse_birth_datetime(t)
    await u.message.reply_text(calculate_age(*p) if p else "❌ نامعتبر", reply_markup=get_date_tools_keyboard())

async def _h_birthday(u, c, t, uid):
    c.user_data.pop("waiting_for", None)
    p = parse_shamsi(t)
    if p:
        y, m, d = p[0], p[1], p[2]; set_birth_date(uid, f"{y}/{m}/{d}")
        await u.message.reply_text(birthday_countdown(y, m, d), reply_markup=get_date_tools_keyboard())
    else:
        await u.message.reply_text("❌ نامعتبر", reply_markup=get_date_tools_keyboard())

async def _h_zodiac(u, c, t, uid):
    c.user_data.pop("waiting_for", None)
    p = parse_shamsi(t)
    await u.message.reply_text(zodiac_animal(p[0], p[1], p[2]) if p else "❌", reply_markup=get_date_tools_keyboard())

async def _h_lunar(u, c, t, uid):
    c.user_data.pop("waiting_for", None)
    p = parse_shamsi(t)
    await u.message.reply_text(lunar_age(p[0], p[1], p[2]) if p else "❌", reply_markup=get_date_tools_keyboard())

async def _h_date_diff(u, c, t, uid):
    c.user_data.pop("waiting_for", None)
    p = parse_two_dates(t)
    await u.message.reply_text(date_diff(*p[0], *p[1]) if p else "❌", reply_markup=get_date_tools_keyboard())

async def _h_age_diff(u, c, t, uid):
    c.user_data.pop("waiting_for", None)
    p = parse_two_dates(t)
    await u.message.reply_text(age_diff(*p[0], *p[1]) if p else "❌", reply_markup=get_date_tools_keyboard())

async def _h_event_search(u, c, t, uid):
    c.user_data.pop("waiting_for", None)
    await u.message.reply_text(search_events(t), reply_markup=get_date_tools_keyboard())

async def _h_countdown(u, c, t, uid):
    c.user_data.pop("waiting_for", None)
    p = parse_countdown(t)
    await u.message.reply_text(custom_countdown(*p) if p else "❌", reply_markup=get_date_tools_keyboard())

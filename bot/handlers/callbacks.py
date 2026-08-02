from telegram import Update
from telegram.ext import ContextTypes
from bot.database import update_user_field, get_user, get_user_city
from bot.utils.helpers import (
    build_message,
    get_main_keyboard,
    get_country_keyboard,
    get_iran_cities_keyboard,
    get_iraq_cities_keyboard,
    get_language_keyboard,
    get_calendar_buttons,
    get_calendar_text,
)
from bot.api.calendar import get_today_tehran
from bot.handlers.middleware import check_and_rate_limit
import jdatetime


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not await check_and_rate_limit(update, context):
        return

    data = query.data
    user_id = update.effective_user.id

    # ── بروزرسانی: همان پیام ویرایش می‌شود ──
    if data == "refresh_main":
        first_name = get_user(user_id)[1] if get_user(user_id) else "کاربر"
        city = get_user_city(user_id)
        message = await build_message(user_id, first_name, city)
        await query.edit_message_text(message, reply_markup=get_main_keyboard())
        return

    if data == "back_to_main":
        first_name = get_user(user_id)[1] if get_user(user_id) else "کاربر"
        city = get_user_city(user_id)
        message = await build_message(user_id, first_name, city)
        await query.edit_message_text(message, reply_markup=get_main_keyboard())
        return

    if data == "city_menu":
        await query.edit_message_text(
            "🏙 کشور را انتخاب کنید:",
            reply_markup=get_country_keyboard()
        )
        return

    if data == "cities_iran":
        await query.edit_message_text(
            "🇮🇷 شهرهای ایران — یکی را انتخاب کنید:",
            reply_markup=get_iran_cities_keyboard()
        )
        return

    if data == "cities_iraq":
        await query.edit_message_text(
            "🇮🇶 شهرهای عراق — یکی را انتخاب کنید:",
            reply_markup=get_iraq_cities_keyboard()
        )
        return

    if data.startswith("city_"):
        parts = data.split("_", 2)
        if len(parts) == 3:
            country = parts[1]
            city = parts[2]
        else:
            city = data.replace("city_", "")
            country = "Iran"
        update_user_field(user_id, "city", city)
        update_user_field(user_id, "country", country)
        first_name = get_user(user_id)[1] if get_user(user_id) else "کاربر"
        message = await build_message(user_id, first_name, city)
        await query.edit_message_text(message, reply_markup=get_main_keyboard())
        return

    if data == "language_menu":
        await query.edit_message_text(
            "🌍 انتخاب زبان / Choose Language / اختر اللغة:",
            reply_markup=get_language_keyboard()
        )
        return

    if data.startswith("lang_"):
        lang_code = data.replace("lang_", "")
        update_user_field(user_id, "language", lang_code)
        first_name = get_user(user_id)[1] if get_user(user_id) else "کاربر"
        city = get_user_city(user_id)
        message = await build_message(user_id, first_name, city)
        await query.edit_message_text(message, reply_markup=get_main_keyboard())
        return

    if data == "calendar_menu" or data == "calendar_today":
        today = get_today_tehran()
        text = get_calendar_text(today.year, today.month, today.day, user_id)
        await query.edit_message_text(
            text,
            reply_markup=get_calendar_buttons(today.year, today.month, today.day, user_id)
        )
        return

    if data.startswith("day_"):
        parts = data.split("_")
        year, month, day = int(parts[1]), int(parts[2]), int(parts[3])
        try:
            jdatetime.date(year, month, day)
        except ValueError:
            if day < 1:
                month -= 1
                if month < 1:
                    month = 12
                    year -= 1
                last_day = jdatetime.date(year, month, 1) - jdatetime.timedelta(days=1)
                day = last_day.day
            else:
                month += 1
                if month > 12:
                    month = 1
                    year += 1
                day = 1
        text = get_calendar_text(year, month, day, user_id)
        await query.edit_message_text(
            text,
            reply_markup=get_calendar_buttons(year, month, day, user_id)
        )
        return

    if data.startswith("cal_"):
        parts = data.split("_")
        year, month, day = int(parts[1]), int(parts[2]), int(parts[3])
        if month < 1:
            month = 12
            year -= 1
        elif month > 12:
            month = 1
            year += 1
        text = get_calendar_text(year, month, day, user_id)
        await query.edit_message_text(
            text,
            reply_markup=get_calendar_buttons(year, month, day, user_id)
        )
        return

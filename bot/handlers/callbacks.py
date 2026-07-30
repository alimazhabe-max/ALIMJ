from telegram import Update
from telegram.ext import ContextTypes
from bot.database import update_user_field, get_user, get_user_city, get_user_language
from bot.utils.texts import get_text
from bot.utils.helpers import build_message, get_city_buttons, get_language_buttons, get_calendar_buttons, get_calendar_text
from bot.api.calendar import get_today_tehran
import jdatetime

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = update.effective_user.id

    if data.startswith("city_"):
        city = data.replace("city_", "")
        update_user_field(user_id, "city", city)
        first_name = get_user(user_id)[1] if get_user(user_id) else "کاربر"
        message = build_message(user_id, first_name, city)
        await query.edit_message_text(message, reply_markup=get_city_buttons(user_id))

    elif data.startswith("lang_"):
        lang_code = data.replace("lang_", "")
        update_user_field(user_id, "language", lang_code)
        first_name = get_user(user_id)[1] if get_user(user_id) else "کاربر"
        city = get_user_city(user_id)
        message = build_message(user_id, first_name, city)
        await query.edit_message_text(message, reply_markup=get_city_buttons(user_id))

    elif data == "language_menu":
        await query.edit_message_text("🌍 انتخاب زبان / Choose Language / اختر اللغة:", reply_markup=get_language_buttons())

    elif data == "calendar_menu":
        today = get_today_tehran()
        text = get_calendar_text(today.year, today.month, today.day, user_id)
        await query.edit_message_text(text, reply_markup=get_calendar_buttons(today.year, today.month, today.day, user_id))

    elif data == "calendar_today":
        today = get_today_tehran()
        text = get_calendar_text(today.year, today.month, today.day, user_id)
        await query.edit_message_text(text, reply_markup=get_calendar_buttons(today.year, today.month, today.day, user_id))

    elif data.startswith("day_"):
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
        await query.edit_message_text(text, reply_markup=get_calendar_buttons(year, month, day, user_id))

    elif data.startswith("cal_"):
        parts = data.split("_")
        year, month, day = int(parts[1]), int(parts[2]), int(parts[3])
        if month < 1:
            month = 12
            year -= 1
        elif month > 12:
            month = 1
            year += 1
        text = get_calendar_text(year, month, day, user_id)
        await query.edit_message_text(text, reply_markup=get_calendar_buttons(year, month, day, user_id))

    elif data == "back_to_main":
        first_name = get_user(user_id)[1] if get_user(user_id) else "کاربر"
        city = get_user_city(user_id)
        message = build_message(user_id, first_name, city)
        await query.edit_message_text(message, reply_markup=get_city_buttons(user_id))

    elif data == "refresh_main":
        first_name = get_user(user_id)[1] if get_user(user_id) else "کاربر"
        city = get_user_city(user_id)
        message = build_message(user_id, first_name, city)
        await query.edit_message_text(message, reply_markup=get_city_buttons(user_id))

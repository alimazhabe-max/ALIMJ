from telegram import Update
from telegram.ext import ContextTypes
from bot.database import update_user_field, get_user_city, set_last_main_msg_id
from bot.utils.helpers import (
    build_message,
    get_main_keyboard,
    get_refresh_button,
    get_country_keyboard,
    get_iran_cities_keyboard,
    get_iraq_cities_keyboard,
    get_language_keyboard,
    get_calendar_text,
    get_calendar_buttons,
    ALL_CITIES,
    CITY_COUNTRY,
)
from bot.api.calendar import get_today_tehran
from bot.handlers.middleware import check_and_rate_limit


async def _send_main(update, context, text, user_id):
    """پیام اصلی با دکمه بروزرسانی زیر آن"""
    msg = await update.message.reply_text(text, reply_markup=get_refresh_button())
    context.user_data["last_main_msg_id"] = msg.message_id
    set_last_main_msg_id(user_id, msg.message_id)
    return msg



async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    if not await check_and_rate_limit(update, context):
        return

    text = update.message.text.strip()
    user_id = update.effective_user.id
    first_name = update.effective_user.first_name or "کاربر"

    if text == "🏙 انتخاب شهر":
        await update.message.reply_text(
            "🏙 کشور را انتخاب کنید:",
            reply_markup=get_country_keyboard()
        )
        return

    if text == "📅 تقویم":
        today = get_today_tehran()
        cal_text = get_calendar_text(today.year, today.month, today.day, user_id)
        await update.message.reply_text(
            cal_text,
            reply_markup=get_calendar_buttons(today.year, today.month, today.day, user_id)
        )
        return

    if text == "🌍 زبان":
        await update.message.reply_text(
            "🌍 زبان خود را انتخاب کنید:",
            reply_markup=get_language_keyboard()
        )
        return

    if text == "🇮🇷 ایران":
        await update.message.reply_text(
            "🇮🇷 شهر خود را انتخاب کنید:",
            reply_markup=get_iran_cities_keyboard()
        )
        return

    if text == "🇮🇶 عراق":
        await update.message.reply_text(
            "🇮🇶 شهر خود را انتخاب کنید:",
            reply_markup=get_iraq_cities_keyboard()
        )
        return

    if text == "🔙 بازگشت":
        city = get_user_city(user_id)
        message = await build_message(user_id, first_name, city)
        await _send_main(update, context, message, user_id)
        return

    if text == "فارسی 🇮🇷":
        update_user_field(user_id, "language", "fa")
        city = get_user_city(user_id)
        message = await build_message(user_id, first_name, city)
        await _send_main(update, context, message, user_id)
        return

    if text == "English 🇬🇧":
        update_user_field(user_id, "language", "en")
        city = get_user_city(user_id)
        message = await build_message(user_id, first_name, city)
        await _send_main(update, context, message, user_id)
        return

    if text == "العربية 🇸🇦":
        update_user_field(user_id, "language", "ar")
        city = get_user_city(user_id)
        message = await build_message(user_id, first_name, city)
        await _send_main(update, context, message, user_id)
        return

    if text in ALL_CITIES:
        country = CITY_COUNTRY.get(text, "Iran")
        update_user_field(user_id, "city", text)
        update_user_field(user_id, "country", country)
        message = await build_message(user_id, first_name, text)
        full = f"✅ شهر شما به **{text}** تغییر کرد.\n\n" + message
        await _send_main(update, context, full, user_id)
        return

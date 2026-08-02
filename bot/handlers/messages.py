from telegram import Update
from telegram.ext import ContextTypes
from telegram.error import BadRequest
from bot.database import update_user_field, get_user_city
from bot.utils.helpers import (
    build_message,
    get_main_keyboard,
    get_country_keyboard,
    get_iran_cities_keyboard,
    get_iraq_cities_keyboard,
    get_language_reply_keyboard,
    get_calendar_text,
    get_calendar_buttons,
    ALL_CITIES,
    CITY_COUNTRY,
)
from bot.api.calendar import get_today_tehran
from bot.handlers.middleware import check_and_rate_limit


async def _send_or_edit_main(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    """
    اگر آخرین پیام اصلی ربات موجود باشد آن را ویرایش می‌کند،
    وگرنه پیام جدید می‌فرستد و message_id را ذخیره می‌کند.
    """
    chat_id = update.effective_chat.id
    last_id = context.user_data.get("last_main_msg_id")

    if last_id:
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=last_id,
                text=text,
            )
            return
        except BadRequest:
            pass
        except Exception:
            pass

    msg = await update.message.reply_text(text, reply_markup=get_main_keyboard())
    context.user_data["last_main_msg_id"] = msg.message_id


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
            reply_markup=get_language_reply_keyboard()
        )
        return

    if text == "🔄 بروزرسانی":
        city = get_user_city(user_id)
        message = await build_message(user_id, first_name, city)
        await _send_or_edit_main(update, context, message)
        try:
            await update.message.delete()
        except Exception:
            pass
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
        msg = await update.message.reply_text(message, reply_markup=get_main_keyboard())
        context.user_data["last_main_msg_id"] = msg.message_id
        return

    if text == "فارسی 🇮🇷":
        update_user_field(user_id, "language", "fa")
        city = get_user_city(user_id)
        message = await build_message(user_id, first_name, city)
        msg = await update.message.reply_text(message, reply_markup=get_main_keyboard())
        context.user_data["last_main_msg_id"] = msg.message_id
        return

    if text == "English 🇬🇧":
        update_user_field(user_id, "language", "en")
        city = get_user_city(user_id)
        message = await build_message(user_id, first_name, city)
        msg = await update.message.reply_text(message, reply_markup=get_main_keyboard())
        context.user_data["last_main_msg_id"] = msg.message_id
        return

    if text == "العربية 🇸🇦":
        update_user_field(user_id, "language", "ar")
        city = get_user_city(user_id)
        message = await build_message(user_id, first_name, city)
        msg = await update.message.reply_text(message, reply_markup=get_main_keyboard())
        context.user_data["last_main_msg_id"] = msg.message_id
        return

    if text in ALL_CITIES:
        country = CITY_COUNTRY.get(text, "Iran")
        update_user_field(user_id, "city", text)
        update_user_field(user_id, "country", country)
        message = await build_message(user_id, first_name, text)
        full = f"✅ شهر شما به **{text}** تغییر کرد.\n\n" + message
        msg = await update.message.reply_text(full, reply_markup=get_main_keyboard())
        context.user_data["last_main_msg_id"] = msg.message_id
        return

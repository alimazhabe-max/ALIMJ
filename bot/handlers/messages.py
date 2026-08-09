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
    get_more_keyboard,
    get_calendar_text,
    get_calendar_buttons,
    ALL_CITIES,
    CITY_COUNTRY,
)
from bot.api.calendar import get_today_tehran
from bot.handlers.middleware import check_and_rate_limit
from bot.utils.converters import (
    parse_date,
    convert_date,
    parse_birth_datetime,
    calculate_age,
)


async def _send_main(update, context, text, user_id):
    """پیام اصلی + دکمه بروزرسانی زیر آن + برگرداندن کیبورد پایین منوی اصلی"""
    context.user_data.pop("waiting_for", None)
    await update.message.reply_text("🏠 منوی اصلی", reply_markup=get_main_keyboard())
    msg = await update.message.reply_text(text, reply_markup=get_refresh_button())
    context.user_data["last_main_msg_id"] = msg.message_id
    set_last_main_msg_id(user_id, msg.message_id)
    return msg


def _is_back(text: str) -> bool:
    t = text.strip()
    return (
        t == "🔙 بازگشت"
        or t == "بازگشت"
        or "بازگشت" in t
        or t.upper() == "BACK"
        or "BACK" in t.upper()
    )


async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    if not await check_and_rate_limit(update, context):
        return

    text = update.message.text.strip()
    user_id = update.effective_user.id
    first_name = update.effective_user.first_name or "کاربر"

    # ── اگر کاربر در حالت انتظار ورودی است ──
    waiting = context.user_data.get("waiting_for")

    if waiting == "date_convert":
        if _is_back(text):
            context.user_data.pop("waiting_for", None)
            await update.message.reply_text(
                "➕ منوی بیشتر:",
                reply_markup=get_more_keyboard(),
            )
            return
        parsed = parse_date(text)
        if not parsed:
            await update.message.reply_text(
                "❌ تاریخ تشخیص داده نشد.\n\n"
                "مثال‌ها:\n"
                "• `1403/05/18` (شمسی)\n"
                "• `2024/08/09` (میلادی)\n"
                "• `15 صفر 1446` (قمری)\n\n"
                "یا «بازگشت» را بزنید.",
                reply_markup=get_more_keyboard(),
            )
            return
        kind, y, m, d = parsed
        result = convert_date(kind, y, m, d)
        context.user_data.pop("waiting_for", None)
        await update.message.reply_text(result, reply_markup=get_more_keyboard())
        return

    if waiting == "age_calc":
        if _is_back(text):
            context.user_data.pop("waiting_for", None)
            await update.message.reply_text(
                "➕ منوی بیشتر:",
                reply_markup=get_more_keyboard(),
            )
            return
        parsed = parse_birth_datetime(text)
        if not parsed:
            await update.message.reply_text(
                "❌ تاریخ تولد نامعتبر است.\n\n"
                "مثال‌ها:\n"
                "• `1375/03/15`\n"
                "• `1375/3/15 14:30` (با ساعت)\n"
                "• `۱۵ فروردین ۱۳۷۵`\n\n"
                "یا «بازگشت» را بزنید.",
                reply_markup=get_more_keyboard(),
            )
            return
        y, m, d, h, mi = parsed
        result = calculate_age(y, m, d, h, mi)
        context.user_data.pop("waiting_for", None)
        await update.message.reply_text(result, reply_markup=get_more_keyboard())
        return

    # ── منوی اصلی ──
    if text == "🏙 انتخاب شهر" or text == "انتخاب شهر":
        await update.message.reply_text(
            "🏙 کشور را انتخاب کنید:",
            reply_markup=get_country_keyboard(),
        )
        return

    if text == "📅 تقویم" or text == "تقویم":
        today = get_today_tehran()
        cal_text = get_calendar_text(today.year, today.month, today.day, user_id)
        await update.message.reply_text(
            cal_text,
            reply_markup=get_calendar_buttons(today.year, today.month, today.day, user_id),
        )
        return

    if text == "🌍 زبان" or text == "زبان":
        await update.message.reply_text(
            "🌍 زبان خود را انتخاب کنید:",
            reply_markup=get_language_keyboard(),
        )
        return

    if text == "➕ بیشتر" or text == "بیشتر":
        await update.message.reply_text(
            "➕ یکی از گزینه‌ها را انتخاب کنید:",
            reply_markup=get_more_keyboard(),
        )
        return

    # ── منوی بیشتر ──
    if text == "🔄 مبدل تاریخ" or text == "مبدل تاریخ":
        context.user_data["waiting_for"] = "date_convert"
        await update.message.reply_text(
            "🔄 **مبدل تاریخ**\n\n"
            "تاریخ مورد نظر را بفرستید:\n\n"
            "• شمسی: `1403/05/18`\n"
            "• میلادی: `2024/08/09`\n"
            "• قمری: `15 صفر 1446`\n\n"
            "ربات آن را به هر سه تقویم تبدیل می‌کند.",
            reply_markup=get_more_keyboard(),
        )
        return

    if text == "🎂 محاسبه سن دقیق" or text == "محاسبه سن دقیق":
        context.user_data["waiting_for"] = "age_calc"
        await update.message.reply_text(
            "🎂 **محاسبه سن دقیق**\n\n"
            "تاریخ تولد شمسی خود را بفرستید:\n\n"
            "• فقط تاریخ: `1375/03/15`\n"
            "• با ساعت: `1375/03/15 14:30`\n\n"
            "سن دقیق به سال، ماه، روز (و ساعت/دقیقه) محاسبه می‌شود.",
            reply_markup=get_more_keyboard(),
        )
        return

    # ── کشور و شهر ──
    if text == "🇮🇷 ایران" or text == "ایران":
        await update.message.reply_text(
            "🇮🇷 شهر خود را انتخاب کنید:",
            reply_markup=get_iran_cities_keyboard(),
        )
        return

    if text == "🇮🇶 عراق" or text == "عراق":
        await update.message.reply_text(
            "🇮🇶 شهر خود را انتخاب کنید:",
            reply_markup=get_iraq_cities_keyboard(),
        )
        return

    # ── بازگشت ──
    if _is_back(text):
        city = get_user_city(user_id)
        message = await build_message(user_id, first_name, city)
        await _send_main(update, context, message, user_id)
        return

    # ── تغییر زبان ──
    if text == "فارسی 🇮🇷" or text.startswith("فارسی"):
        update_user_field(user_id, "language", "fa")
        city = get_user_city(user_id)
        message = await build_message(user_id, first_name, city)
        await _send_main(update, context, message, user_id)
        return

    if text == "English 🇬🇧" or text.startswith("English"):
        update_user_field(user_id, "language", "en")
        city = get_user_city(user_id)
        message = await build_message(user_id, first_name, city)
        await _send_main(update, context, message, user_id)
        return

    if text == "العربية 🇸🇦" or "العربية" in text or "العربيه" in text:
        update_user_field(user_id, "language", "ar")
        city = get_user_city(user_id)
        message = await build_message(user_id, first_name, city)
        await _send_main(update, context, message, user_id)
        return

    # ── انتخاب شهر ──
    if text in ALL_CITIES:
        country = CITY_COUNTRY.get(text, "Iran")
        update_user_field(user_id, "city", text)
        update_user_field(user_id, "country", country)
        message = await build_message(user_id, first_name, text)
        full = f"✅ شهر شما به **{text}** تغییر کرد.\n\n" + message
        await _send_main(update, context, full, user_id)
        return

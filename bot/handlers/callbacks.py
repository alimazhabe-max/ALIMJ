from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from bot.database import get_user, get_user_city, set_last_main_msg_id
from bot.services.ai_service import clear_history
from bot.services.ai_models import (
    models_keyboard, assistant_keyboard, assistant_intro,
    current_model_title, set_user_model_id, find_model, AUTO_ID,
)
from bot.utils.helpers import (
    build_message,
    get_refresh_button,
    get_main_keyboard,
    get_more_keyboard,
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


    if data == "ai_models":
        try:
            await query.edit_message_text(
                "🎛 <b>انتخاب مدل هوش مصنوعی</b>\n\n"
                f"مدل فعلی: <b>{current_model_title(user_id)}</b>\n"
                "مدل‌های 🔒 نیاز به تنظیم کلید دارند.",
                parse_mode="HTML",
                reply_markup=models_keyboard(user_id),
            )
        except Exception:
            await query.message.reply_text(
                "🎛 انتخاب مدل هوش مصنوعی:",
                reply_markup=models_keyboard(user_id),
            )
        return

    if data == "ai_locked":
        await query.answer("🔒 برای این مدل کلید API تنظیم نشده است.", show_alert=True)
        return

    if data.startswith("ai_set:"):
        model_id = data.split(":", 1)[1]
        set_user_model_id(user_id, model_id)
        context.user_data["ai_mode"] = True
        model = find_model(model_id)
        await query.answer(
            "✅ " + ("خودکار" if model_id == AUTO_ID else model["name"] if model else "انتخاب شد"),
        )
        try:
            await query.edit_message_text(
                "🎛 <b>انتخاب مدل هوش مصنوعی</b>\n\n"
                f"مدل فعلی: <b>{current_model_title(user_id)}</b>\n"
                "حالا پیامت را بفرست 👇",
                parse_mode="HTML",
                reply_markup=models_keyboard(user_id),
            )
        except Exception:
            pass
        return

    if data == "ai_start":
        context.user_data["ai_mode"] = True
        await query.message.reply_text(
            assistant_intro(user_id),
            parse_mode="HTML",
            reply_markup=assistant_keyboard(user_id),
        )
        return

    if data == "ai_clear_memory":
        clear_history(user_id)
        await query.answer("حافظه AI پاک شد ✅", show_alert=False)
        await query.message.reply_text(
            "🧹 حافظه کوتاه‌مدت گفت‌وگو پاک شد. از نو شروع کن!",
            reply_markup=assistant_keyboard(user_id),
        )
        return

    if data == "ai_exit":
        context.user_data.pop("ai_mode", None)
        context.user_data.pop("waiting_for", None)
        await query.message.reply_text("🏠 منوی اصلی", reply_markup=get_main_keyboard())
        return

    # بروزرسانی = ویرایش همان پیام
    if data == "refresh_main":
        first_name = get_user(user_id)[1] if get_user(user_id) else "کاربر"
        city = get_user_city(user_id)
        message = await build_message(user_id, first_name, city)
        await query.edit_message_text(message, reply_markup=get_refresh_button())
        context.user_data["last_main_msg_id"] = query.message.message_id
        set_last_main_msg_id(user_id, query.message.message_id)
        return

    if data == "back_to_main":
        first_name = get_user(user_id)[1] if get_user(user_id) else "کاربر"
        city = get_user_city(user_id)
        message = await build_message(user_id, first_name, city)
        msg = await query.message.reply_text(message, reply_markup=get_refresh_button())
        context.user_data["last_main_msg_id"] = msg.message_id
        set_last_main_msg_id(user_id, msg.message_id)
        try:
            await query.message.delete()
        except Exception:
            pass
        return

    if data == "calendar_today":
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

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from bot.database import get_user, get_user_city, set_last_main_msg_id
from bot.services.ai_service import clear_history, available_model_options, set_selected_model, get_selected_model
from bot.utils.helpers import (
    build_message,
    get_refresh_button,
    get_main_keyboard, get_ai_keyboard, get_ai_model_keyboard,
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
        await query.edit_message_reply_markup(reply_markup=get_ai_model_keyboard(user_id))
        return

    if data == "ai_models_back":
        await query.edit_message_reply_markup(reply_markup=get_ai_keyboard(user_id))
        return

    if data == "ai_noop":
        await query.answer("هیچ مدل فعالی تنظیم نشده است.", show_alert=True)
        return

    if data.startswith("ai_model:"):
        try:
            index = int(data.split(":", 1)[1])
            options = available_model_options()
            provider, _label, model = options[index]
        except (ValueError, IndexError):
            await query.answer("❌ این مدل دیگر در دسترس نیست.", show_alert=True)
            return
        set_selected_model(user_id, provider, model)
        await query.answer(f"مدل انتخاب شد: {model}", show_alert=False)
        await query.edit_message_reply_markup(reply_markup=get_ai_keyboard(user_id))
        return

    if data == "ai_clear_memory":
        clear_history(user_id)
        await query.answer("حافظه AI پاک شد ✅", show_alert=False)
        try:
            await query.edit_message_reply_markup(
                reply_markup=get_ai_keyboard(user_id)
            )
        except Exception:
            pass
        await query.message.reply_text("✅ حافظه کوتاه‌مدت گفت‌وگوی AI پاک شد.")
        return

    if data == "ai_exit":
        context.user_data.pop("ai_mode", None)
        context.user_data.pop("waiting_for", None)
        await query.answer()
        await query.message.reply_text("➕ منوی بیشتر:", reply_markup=get_more_keyboard())
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

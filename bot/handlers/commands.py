from telegram import Update, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from bot.database import (
    get_user,
    save_user,
    get_all_users,
    get_user_city,
    get_user_language,
    update_user_field
)
from bot.utils.texts import get_text, TEXTS
from bot.utils.helpers import (
    build_message,
    get_city_buttons,
    get_language_buttons,
    get_calendar_buttons,
    get_calendar_text,
)
from bot.config import config
from bot.logger import logger
import asyncio

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """دستور /start - بدون هیچ چکی"""
    user = update.effective_user
    user_id = user.id
    first_name = user.first_name or "کاربر"
    save_user(user_id, first_name)
    city = get_user_city(user_id)
    message = build_message(user_id, first_name, city)
    await update.message.reply_text(message, reply_markup=get_city_buttons(user_id))

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """دستور /help"""
    if not await check_and_rate_limit(update, context):
        return
    user_id = update.effective_user.id
    await update.message.reply_text(get_text(user_id, "help"))

async def city_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """دستور /city [نام شهر]"""
    if not await check_and_rate_limit(update, context):
        return
    user_id = update.effective_user.id
    args = context.args
    if not args:
        await update.message.reply_text("❌ لطفاً نام شهر را وارد کن. مثال: `/city مشهد`")
        return
    new_city = " ".join(args)
    update_user_field(user_id, "city", new_city)
    await update.message.reply_text(get_text(user_id, "city_changed", city=new_city))

async def language_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """دستور /language"""
    if not await check_and_rate_limit(update, context):
        return
    user_id = update.effective_user.id
    await update.message.reply_text(
        "🌍 زبان خود را انتخاب کنید / Choose your language / اختر لغتك:",
        reply_markup=get_language_buttons()
    )

async def calendar_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """دستور /calendar"""
    if not await check_and_rate_limit(update, context):
        return
    user_id = update.effective_user.id
    from bot.api.calendar import get_today_tehran
    today = get_today_tehran()
    text = get_calendar_text(today.year, today.month, today.day, user_id)
    await update.message.reply_text(text, reply_markup=get_calendar_buttons(today.year, today.month, today.day, user_id))

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """دستور /stats - فقط برای ادمین"""
    if not await check_and_rate_limit(update, context):
        return
    user_id = update.effective_user.id
    if user_id not in config.ADMIN_IDS:
        await update.message.reply_text(get_text(user_id, "admin_only"))
        return
    from database import get_db_connection
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users")
    total = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM users WHERE subscribed = 1")
    active = c.fetchone()[0]
    conn.close()
    await update.message.reply_text(get_text(user_id, "stats", total=total, active=active))

async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """دستور /broadcast [پیام] - فقط برای ادمین"""
    if not await check_and_rate_limit(update, context):
        return
    user_id = update.effective_user.id
    if user_id not in config.ADMIN_IDS:
        await update.message.reply_text(get_text(user_id, "admin_only"))
        return
    if not context.args:
        await update.message.reply_text("❌ لطفاً پیام را وارد کن. مثال: `/broadcast سلام به همه`")
        return
    message_text = " ".join(context.args)
    users = get_all_users()
    count = 0
    for user in users:
        try:
            await context.bot.send_message(chat_id=user[0], text=message_text)
            count += 1
            await asyncio.sleep(0.1)
        except Exception as e:
            logger.error(f"Broadcast failed to {user[0]}: {e}")
    await update.message.reply_text(get_text(user_id, "broadcast_sent", count=count))

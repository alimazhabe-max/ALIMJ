from collections import defaultdict
import time
from telegram import Update
from telegram.ext import ContextTypes
from config import config
from logger import logger
from database import get_user, save_user
from utils.texts import get_text, TEXTS

user_requests = defaultdict(list)

async def rate_limit_middleware(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user:
        return True
    user_id = update.effective_user.id
    now = time.time()
    user_requests[user_id] = [t for t in user_requests[user_id] if now - t < 60]
    if len(user_requests[user_id]) >= config.RATE_LIMIT:
        await update.message.reply_text("⏳ لطفاً کمی صبر کنید. درخواست‌های زیادی ارسال کردید.")
        logger.warning(f"Rate limit exceeded for user {user_id}")
        return False
    user_requests[user_id].append(now)
    return True

async def check_membership(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user:
        return False
    user_id = update.effective_user.id
    try:
        member = await context.bot.get_chat_member(config.REQUIRED_CHANNEL_ID, user_id)
        if member.status in ["member", "administrator", "creator"]:
            return True
    except Exception as e:
        logger.error(f"Membership check failed for {user_id}: {e}")
    return False

async def ensure_user_registered(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user:
        return
    user = update.effective_user
    if not get_user(user.id):
        save_user(user.id, user.first_name or "کاربر")
        logger.info(f"New user registered: {user.id}")

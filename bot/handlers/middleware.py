from collections import defaultdict
import time
from telegram import Update
from telegram.ext import ContextTypes
from config import config
from logger import logger
from database import get_user, save_user, get_user_language
from utils.texts import TEXTS

user_requests = defaultdict(list)

async def rate_limit_middleware(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """محدودیت نرخ درخواست‌ها (۱۰ درخواست در دقیقه)"""
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
    """بررسی عضویت کاربر در کانال اجباری"""
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
    """ثبت کاربر در دیتابیس در صورت عدم وجود"""
    if not update.effective_user:
        return
    user = update.effective_user
    if not get_user(user.id):
        save_user(user.id, user.first_name or "کاربر")
        logger.info(f"New user registered: {user.id}")

async def check_and_rate_limit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """
    تابع کمکی برای استفاده در هر هندلر (به جز /start)
    ثبت کاربر، بررسی عضویت و محدودیت نرخ را انجام می‌دهد.
    در صورت موفقیت True برمی‌گرداند، در غیر این صورت False.
    """
    if not update.effective_user:
        return False

    # ثبت کاربر در دیتابیس
    await ensure_user_registered(update, context)

    # بررسی عضویت در کانال (برای دستورات غیر از /start)
    if update.message and update.message.text != "/start":
        if not await check_membership(update, context):
            lang = get_user_language(update.effective_user.id)
            await update.message.reply_text(
                TEXTS[lang]["not_member"].format(channel_link=config.REQUIRED_CHANNEL_LINK)
            )
            return False

    # بررسی محدودیت نرخ
    if not await rate_limit_middleware(update, context):
        return False

    return True

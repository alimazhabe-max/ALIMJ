from collections import defaultdict
import time
from telegram import Update
from telegram.ext import ContextTypes
from bot.config import config
from bot.logger import logger
from bot.database import get_user, save_user, get_user_language
from bot.utils.texts import TEXTS

user_requests = defaultdict(list)

async def rate_limit_middleware(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """محدودیت نرخ درخواست‌ها — پیش‌فرض ۶۰ در دقیقه (قابل تنظیم با RATE_LIMIT)"""
    if not update.effective_user:
        return True

    user_id = update.effective_user.id

    # ادمین‌ها محدودیت ندارند
    if user_id in getattr(config, "ADMIN_IDS", []):
        return True

    now = time.time()
    # فقط درخواست‌های ۶۰ ثانیه اخیر را نگه دار
    user_requests[user_id] = [t for t in user_requests[user_id] if now - t < 60]

    limit = getattr(config, "RATE_LIMIT", 60)
    if len(user_requests[user_id]) >= limit:
        remaining = 60 - int(now - user_requests[user_id][0]) if user_requests[user_id] else 5
        remaining = max(1, min(remaining, 60))
        text = f"⏳ کمی سریع زدید.\nلطفاً حدود {remaining} ثانیه صبر کنید و دوباره امتحان کنید."
        try:
            if update.message:
                await update.message.reply_text(text)
            elif update.callback_query:
                await update.callback_query.answer(text, show_alert=True)
        except Exception:
            pass
        logger.warning(f"Rate limit exceeded for user {user_id} ({len(user_requests[user_id])}/{limit})")
        return False

    user_requests[user_id].append(now)
    return True

async def check_membership(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """بررسی عضویت کاربر در کانال اجباری"""
    if not update.effective_user:
        return False
    user_id = update.effective_user.id
    # ادمین از عضویت معاف
    if user_id in getattr(config, "ADMIN_IDS", []):
        return True
    try:
        member = await context.bot.get_chat_member(config.REQUIRED_CHANNEL_ID, user_id)
        if member.status in ["member", "administrator", "creator"]:
            return True
    except Exception as e:
        logger.error(f"Membership check failed for {user_id}: {e}")
        # در صورت خطای API کانال، اجازه بده (تا ربات گیر نکند)
        return True
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
    """
    if not update.effective_user:
        return False

    await ensure_user_registered(update, context)

    # بررسی عضویت (برای همه به جز /start)
    is_start = (
        update.message
        and update.message.text
        and update.message.text.startswith("/start")
    )
    if not is_start:
        if not await check_membership(update, context):
            lang = get_user_language(update.effective_user.id)
            text = TEXTS.get(lang, TEXTS["fa"])["not_member"].format(
                channel_link=config.REQUIRED_CHANNEL_LINK
            )
            if update.message:
                await update.message.reply_text(text)
            elif update.callback_query:
                await update.callback_query.answer("لطفاً ابتدا در کانال عضو شوید", show_alert=True)
                try:
                    await update.callback_query.message.reply_text(text)
                except Exception:
                    pass
            return False

    if not await rate_limit_middleware(update, context):
        return False

    return True

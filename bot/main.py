from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes,
)
from telegram import Update
from bot.config import config
from bot.logger import logger
from bot.database import init_db, backup_db, _user_count, DB_PATH
from bot.handlers.commands import (
    start, help_command, city_command, language_command,
    calendar_command, stats_command, broadcast_command,
    backup_command, restore_document_handler,
)
from bot.handlers.callbacks import button_handler
from bot.handlers.messages import text_handler
from bot.scheduler import setup_scheduler
from bot.db_persist import notify_admins_if_empty, send_db_to_admins
import threading
from flask import Flask
import os
from datetime import datetime
import asyncio

flask_app = Flask(__name__)


@flask_app.route("/")
def home():
    return "✅ Bot is running!"


@flask_app.route("/health")
def health():
    return {
        "status": "ok",
        "time": str(datetime.now()),
        "users": _user_count(DB_PATH),
        "db": str(DB_PATH),
    }


def run_flask():
    port = int(os.environ.get("PORT", 8080))
    flask_app.run(host="0.0.0.0", port=port, use_reloader=False, threaded=True)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    err = context.error
    ignore_names = (
        "NetworkError", "TimedOut", "RetryAfter", "BadGateway",
        "ServiceUnavailable", "RequestTimeout", "httpx",
    )
    err_name = type(err).__name__ if err else ""
    err_str = str(err) or ""
    if any(x in err_name or x in err_str for x in ignore_names):
        logger.warning(f"Ignored transient error: {err_name}: {err_str[:120]}")
        return

    logger.error("Exception while handling an update:", exc_info=err)

    try:
        if not update or not isinstance(update, Update) or not update.effective_user:
            return
        uid = update.effective_user.id
        now = datetime.now().timestamp()
        last = getattr(error_handler, "_last", {})
        if now - last.get(uid, 0) < 30:
            return
        last[uid] = now
        error_handler._last = last

        if update.effective_message:
            await update.effective_message.reply_text(
                "⚠️ موقتاً مشکلی پیش آمد. چند ثانیه بعد دوباره امتحان کنید."
            )
    except Exception:
        pass


async def post_init(app: Application):
    """بعد از استارت — اگر DB خالی بود به ادمین خبر بده"""
    try:
        await notify_admins_if_empty(app.bot)
    except Exception as e:
        logger.error(f"post_init notify: {e}")


def main():
    logger.info("=" * 50)
    logger.info("🚀 Starting Rooze Ziba Bot")
    logger.info(f"DB path: {DB_PATH}")
    logger.info("=" * 50)

    init_db()
    backup_db()

    app = (
        Application.builder()
        .token(config.BOT_TOKEN)
        .concurrent_updates(True)
        .post_init(post_init)
        .build()
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("city", city_command))
    app.add_handler(CommandHandler("language", language_command))
    app.add_handler(CommandHandler("calendar", calendar_command))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("broadcast", broadcast_command))
    app.add_handler(CommandHandler("backup", backup_command))
    # ریستور: فایل .db با کپشن /restore
    app.add_handler(MessageHandler(filters.Document.ALL, restore_document_handler))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    app.add_error_handler(error_handler)

    setup_scheduler(app)

    # Flask برای healthcheck
    t = threading.Thread(target=run_flask, daemon=True)
    t.start()

    logger.info("✅ Bot ready (Telegram backup/restore enabled)")
    app.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()

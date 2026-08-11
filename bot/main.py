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
from bot.db_persist import (
    notify_admins_if_empty,
    send_db_to_admins,
    auto_backup,
)
import threading
import signal
import sys
from flask import Flask
import os
from datetime import datetime

flask_app = Flask(__name__)

# نگه داشتن رفرنس اپ برای بکاپ هنگام خاموش شدن
_app_ref = {"app": None}
_shutdown_backup_done = {"done": False}


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
    try:
        await notify_admins_if_empty(app.bot)
    except Exception as e:
        logger.error(f"post_init notify: {e}")


async def pre_shutdown_backup(app: Application):
    """
    قبل از خاموش شدن (دیپلوی / ری‌استارت):
    ۱) بکاپ GitHub
    ۲) ارسال فایل برای ادمین در تلگرام
    """
    if _shutdown_backup_done["done"]:
        return
    _shutdown_backup_done["done"] = True
    logger.info("🛑 Shutdown detected — sending backup to admin + GitHub...")
    try:
        ok, msg = auto_backup()
        logger.info(f"shutdown GitHub backup: {msg}")
    except Exception as e:
        logger.error(f"shutdown GitHub backup failed: {e}")
    try:
        ok, msg = await send_db_to_admins(
            app.bot,
            caption=(
                "💾 بکاپ خودکار قبل از خاموش شدن / دیپلوی\n"
                f"👥 کاربران: {_user_count(DB_PATH)}\n"
                f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
                "اگر بعد از دیپلوی داده برگشت نشد، همین فایل را با کپشن /restore بفرست."
            ),
        )
        logger.info(f"shutdown telegram backup: {msg}")
    except Exception as e:
        logger.error(f"shutdown telegram backup failed: {e}")


async def post_shutdown(app: Application):
    await pre_shutdown_backup(app)


def _sync_shutdown_backup():
    """برای سیگنال SIGTERM — اگر event loop در دسترس نبود"""
    if _shutdown_backup_done["done"]:
        return
    try:
        ok, msg = auto_backup()
        logger.info(f"signal GitHub backup: {msg}")
    except Exception as e:
        logger.error(f"signal backup failed: {e}")


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
        .post_shutdown(post_shutdown)
        .build()
    )
    _app_ref["app"] = app

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("city", city_command))
    app.add_handler(CommandHandler("language", language_command))
    app.add_handler(CommandHandler("calendar", calendar_command))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("broadcast", broadcast_command))
    app.add_handler(CommandHandler("backup", backup_command))
    app.add_handler(MessageHandler(filters.Document.ALL, restore_document_handler))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    app.add_error_handler(error_handler)
    setup_scheduler(app)

    t = threading.Thread(target=run_flask, daemon=True)
    t.start()

    # Render موقع دیپلوی SIGTERM می‌فرستد
    def _on_signal(signum, frame):
        logger.warning(f"Received signal {signum} — backup then exit")
        _sync_shutdown_backup()
        # اجازه بده run_polling خودش با post_shutdown تمام کند
        try:
            app.stop()
        except Exception:
            pass

    try:
        signal.signal(signal.SIGTERM, _on_signal)
        signal.signal(signal.SIGINT, _on_signal)
    except Exception as e:
        logger.warning(f"signal handler setup: {e}")

    logger.info("✅ Bot ready (pre-deploy backup to admin enabled)")
    app.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()

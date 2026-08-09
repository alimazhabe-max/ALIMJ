from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from telegram import Update
from bot.config import config
from bot.logger import logger
from bot.database import init_db, backup_db
from bot.handlers.commands import (
    start, help_command, city_command, language_command,
    calendar_command, stats_command, broadcast_command
)
from bot.handlers.callbacks import button_handler
from bot.handlers.messages import text_handler
from bot.scheduler import setup_scheduler
import threading
from flask import Flask
import os
from datetime import datetime
import traceback

flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    return "✅ Bot is running!"

@flask_app.route('/health')
def health():
    return {"status": "ok", "time": str(datetime.now())}

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    flask_app.run(host='0.0.0.0', port=port, use_reloader=False, threaded=True)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """جلوگیری از کرش کامل ربات — همه خطاها لاگ و به کاربر پیام دوستانه"""
    logger.error("Exception while handling an update:", exc_info=context.error)
    try:
        if update and isinstance(update, Update) and update.effective_message:
            await update.effective_message.reply_text(
                "⚠️ خطایی رخ داد. لطفاً دوباره امتحان کنید.\n"
                "اگر مشکل ادامه داشت، چند لحظه صبر کنید."
            )
    except Exception:
        pass


def main():
    logger.info("=" * 50)
    logger.info("🚀 Starting ALIMJ Bot v3.0 - Professional + Crypto + Weather 7d")
    logger.info("=" * 50)

    init_db()
    backup_db()

    app = (
        Application.builder()
        .token(config.BOT_TOKEN)
        .concurrent_updates(True)  # سرعت بالاتر
        .build()
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("city", city_command))
    app.add_handler(CommandHandler("language", language_command))
    app.add_handler(CommandHandler("calendar", calendar_command))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("broadcast", broadcast_command))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    app.add_error_handler(error_handler)

    setup_scheduler(app)

    logger.info("✅ Bot is fully ready! (no-crash + fast mode)")

    app.run_polling(
        allowed_updates=["message", "callback_query"],
        drop_pending_updates=True,
        close_loop=False,
    )


if __name__ == "__main__":
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    main()

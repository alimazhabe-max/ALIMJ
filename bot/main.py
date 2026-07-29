from telegram.ext import Application, CommandHandler, CallbackQueryHandler
from config import config
from logger import logger
from database import init_db, backup_db
from handlers.commands import start, help_command, city_command, language_command, calendar_command, stats_command, broadcast_command
from handlers.callbacks import button_handler
from scheduler import setup_scheduler
import asyncio
import threading
from flask import Flask
import os
from datetime import datetime

# Flask app for health checks (required for Render)
flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    return "✅ Bot is running!"

@flask_app.route('/health')
def health():
    return {"status": "ok", "time": str(datetime.now())}

def run_flask():
    flask_app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))

async def main():
    logger.info("=" * 50)
    logger.info("🚀 Starting Prayer Times Bot v2.0 - Professional Edition")
    logger.info("=" * 50)

    # Initialize database
    init_db()
    backup_db()

    # Build application
    app = Application.builder().token(config.BOT_TOKEN).build()

    # Register command handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("city", city_command))
    app.add_handler(CommandHandler("language", language_command))
    app.add_handler(CommandHandler("calendar", calendar_command))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("broadcast", broadcast_command))
    app.add_handler(CallbackQueryHandler(button_handler))

    # Setup scheduler
    setup_scheduler(app)

    logger.info("✅ Bot is fully ready!")
    await app.run_polling(allowed_updates=["message", "callback_query"])

if __name__ == "__main__":
    # Run Flask in background for health checks
    threading.Thread(target=run_flask, daemon=True).start()
    # Run the bot
    asyncio.run(main())

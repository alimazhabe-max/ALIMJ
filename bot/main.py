from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes,
)
from telegram import Update
from bot.config import config
from bot.release import version_string
from bot.logger import logger
from bot.database import init_db, backup_db, _user_count, DB_PATH
from bot.handlers.commands import (
    start, help_command, city_command, language_command,
    calendar_command, stats_command, broadcast_command,
    backup_command, restore_document_handler, diagnostics_command, knowledge_command, agent_command,
    memory_command, automation_command, plugins_command,
)
from bot.handlers.callbacks import button_handler
from bot.handlers.messages import text_handler, media_ai_handler, voice_ai_handler, lens_command
from bot.scheduler import setup_scheduler
from bot.db_persist import notify_admins_if_empty, shutdown_backup
import threading
import signal
from flask import Flask, request
import os
from datetime import datetime
import hmac

flask_app = Flask(__name__)
_shutdown_done = {"done": False}


@flask_app.route("/")
def home():
    return "✅ Bot is running!"


def _metrics_authorized():
    """Protect operational telemetry; fail closed when a token is configured."""
    token = getattr(config, "METRICS_TOKEN", "")
    if not token:
        return False
    supplied = request.headers.get("X-Metrics-Token", "")
    return bool(supplied) and hmac.compare_digest(supplied, token)


@flask_app.route("/metrics")
def metrics():
    from flask import jsonify
    if not _metrics_authorized():
        return jsonify({"error": "unauthorized"}), 401
    from bot.utils.observability import snapshot
    return jsonify(snapshot())


@flask_app.route("/health")
def health():
    # Never expose filesystem paths, admin IDs, or internal database details publicly.
    from bot.release import APP_NAME, VERSION, RELEASE_CHANNEL
    deployment_id = getattr(config, "DEPLOYMENT_ID", "")
    return {
        "status": "ok",
        "app": APP_NAME,
        "version": VERSION,
        "channel": RELEASE_CHANNEL,
        "deployment": deployment_id[:12] if deployment_id else "unknown",
        "time": str(datetime.now()),
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
        from bot.utils.observability import record_error
        record_error("telegram_update", err)
    except Exception:
        pass
    try:
        if not update or not isinstance(update, Update) or not update.effective_user:
            return
        uid = update.effective_user.id
        now = datetime.now().timestamp()
        last = getattr(error_handler, "_last", {})
        if now - last.get(uid, 0) < 30:
            return
        last[uid] = now
        # Bound the per-user error throttle map so a long-running bot does not
        # retain one timestamp forever for every historical user.
        if len(last) > 4096:
            cutoff = now - 86400
            last = {k: v for k, v in last.items() if v >= cutoff}
        error_handler._last = last
        if update.effective_message:
            await update.effective_message.reply_text(
                "⚠️ موقتاً مشکلی پیش آمد. چند ثانیه بعد دوباره امتحان کنید."
            )
    except Exception:
        pass


async def post_init(app: Application):
    try:
        from bot.plugins import register_builtin_plugins, start_enabled
        register_builtin_plugins()
        start_enabled()
        logger.info("🔌 Plugins initialized")
    except Exception as e:
        logger.warning(f"Plugin initialization: {e}")
    try:
        await notify_admins_if_empty(app.bot)
    except Exception as e:
        logger.error(f"post_init notify: {e}")


def _do_shutdown_backup(reason: str = "shutdown"):
    if _shutdown_done["done"]:
        return
    _shutdown_done["done"] = True
    logger.info(f"🛑 {reason} — backup to admin + GitHub...")
    try:
        msg = shutdown_backup()
        logger.info(f"shutdown_backup result: {msg}")
    except Exception as e:
        logger.error(f"shutdown_backup failed: {e}")


async def post_shutdown(app: Application):
    _do_shutdown_backup("post_shutdown")
    try:
        from bot.plugins import stop_enabled
        stop_enabled()
    except Exception as e:
        logger.warning(f"Plugin shutdown: {e}")
    try:
        from bot.utils.task_manager import shutdown as shutdown_tasks
        await shutdown_tasks(timeout=float(os.environ.get("TASK_SHUTDOWN_TIMEOUT", "5")))
    except Exception as e:
        logger.warning(f"Background task shutdown: {e}")
    try:
        from bot.services.ai_tools import clear_tool_cache
        clear_tool_cache()
    except Exception as e:
        logger.warning(f"Tool cache cleanup: {e}")
    try:
        from bot.utils.http_client import clear_http_cache
        clear_http_cache()
    except Exception as e:
        logger.warning(f"HTTP cache cleanup: {e}")
    try:
        from bot.services.ai_service import close_http
        await close_http()
    except Exception as e:
        logger.warning(f"AI HTTP client close: {e}")


def startup_self_check() -> None:
    """Fail fast on broken deployment wiring before Telegram polling starts."""
    checks = []
    required_commands = (
        "start", "help_command", "city_command", "language_command",
        "calendar_command", "stats_command", "broadcast_command",
        "backup_command", "restore_document_handler", "diagnostics_command",
        "knowledge_command", "agent_command", "memory_command",
        "automation_command", "plugins_command",
    )
    from bot.handlers import commands as command_module
    for name in required_commands:
        checks.append((f"command:{name}", callable(getattr(command_module, name, None))))

    from bot.handlers import callbacks as callbacks_module
    checks.append(("callback:button_handler", callable(getattr(callbacks_module, "button_handler", None))))

    from bot.handlers import messages as messages_module
    for name in ("text_handler", "media_ai_handler", "voice_ai_handler", "lens_command"):
        checks.append((f"message:{name}", callable(getattr(messages_module, name, None))))

    # Validate the high-frequency UI/feature symbols too. These are imported lazily
    # by handlers, so checking them at startup prevents production-only NameError/ImportError.
    from bot.utils import keyboard_factory as keyboard_module
    required_keyboards = (
        "get_main_keyboard", "get_more_keyboard", "get_country_keyboard",
        "get_language_keyboard", "get_iran_cities_keyboard", "get_iraq_cities_keyboard",
        "get_font_keyboard", "get_font_en_keyboard", "get_date_tools_keyboard",
        "get_tools_keyboard", "get_market_keyboard", "get_profile_keyboard",
    )
    for name in required_keyboards:
        checks.append((f"keyboard:{name}", callable(getattr(keyboard_module, name, None))))

    # Execute every zero/low-side-effect keyboard constructor. This catches
    # runtime NameError/ImportError issues (e.g. missing Telegram classes)
    # that AST/callable checks cannot detect. User-specific/stateful flows are
    # intentionally excluded from startup to avoid touching the database.
    smoke_keyboards = (
        "get_main_keyboard", "get_ai_keyboard", "get_ai_model_keyboard",
        "get_more_keyboard", "get_date_tools_keyboard", "get_religious_keyboard",
        "get_market_keyboard", "get_weather_geo_keyboard", "get_tools_keyboard",
        "get_azan_keyboard", "get_fun_keyboard", "get_joke_keyboard",
        "get_profile_keyboard", "get_smart_settings_keyboard", "get_country_keyboard",
        "get_iran_cities_keyboard", "get_iraq_cities_keyboard", "get_language_keyboard",
        "get_font_keyboard", "get_font_en_keyboard", "get_font_fa_keyboard",
    )
    for name in smoke_keyboards:
        constructor = getattr(keyboard_module, name, None)
        if not callable(constructor):
            raise RuntimeError(f"Runtime smoke missing keyboard: {name}")
        try:
            markup = constructor()
            if markup is None:
                raise RuntimeError("returned None")
        except Exception as exc:
            raise RuntimeError(f"Runtime smoke failed for keyboard:{name}: {type(exc).__name__}: {exc}") from exc
    logger.info("🔥 Runtime smoke passed (%d keyboard constructors)", len(smoke_keyboards))

    from bot.handlers import feature_handlers as feature_module
    # These are the actual public feature handlers currently exposed by the
    # modular feature handler module. Keep this list aligned with messages.py
    # rather than checking legacy facade names that no longer exist.
    required_features = (
        "_h_date_convert", "_h_age_calc", "_h_birthday", "_h_zodiac",
        "_h_lunar", "_h_date_diff", "_h_age_diff", "_h_event_search",
        "_h_countdown", "_h_calc", "_h_profit", "_h_currency",
        "_h_crypto_full", "_h_crypto_pos", "_h_crypto_chart",
        "_h_crypto_analyze", "_h_distance", "_h_birth_save",
        "_h_count_text", "_h_font_text", "_h_font_all",
    )
    for name in required_features:
        checks.append((f"feature:{name}", callable(getattr(feature_module, name, None))))

    checks.append(("database:init_db", callable(init_db)))
    checks.append(("database:backup_db", callable(backup_db)))

    failed = [name for name, ok in checks if not ok]
    if failed:
        raise RuntimeError("Startup self-check failed: " + ", ".join(failed))

    expected = getattr(config, "RELEASE_VERSION", "")
    actual = version_string()
    if expected and expected not in actual:
        raise RuntimeError(f"RELEASE_VERSION mismatch: expected {expected}, running {actual}")
    logger.info("✅ Startup self-check passed (%d checks)", len(checks))


def main():
    logger.info("=" * 50)
    logger.info(f"🚀 Starting {version_string()}")
    logger.info(f"DB path: {DB_PATH}")
    logger.info(f"ADMIN_IDS: {config.ADMIN_IDS}")
    logger.info("=" * 50)
    logger.info("Deployment ID: %s", getattr(config, "DEPLOYMENT_ID", "")[:12] or "unknown")
    if getattr(config, "STARTUP_CHECK", True):
        startup_self_check()

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

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("lens", lens_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("city", city_command))
    app.add_handler(CommandHandler("language", language_command))
    app.add_handler(CommandHandler("calendar", calendar_command))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("diagnostics", diagnostics_command))
    app.add_handler(CommandHandler("knowledge", knowledge_command))
    app.add_handler(CommandHandler("memory", memory_command))
    app.add_handler(CommandHandler("automation", automation_command))
    app.add_handler(CommandHandler("agent", agent_command))
    app.add_handler(CommandHandler("plugins", plugins_command))
    app.add_handler(CommandHandler("broadcast", broadcast_command))
    app.add_handler(CommandHandler("backup", backup_command))
    app.add_handler(MessageHandler(filters.Document.ALL, restore_document_handler), group=0)
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(
        MessageHandler(filters.PHOTO | filters.VIDEO | filters.VIDEO_NOTE | filters.Document.ALL, media_ai_handler),
        group=1,
    )
    app.add_handler(
        MessageHandler(filters.VOICE | filters.AUDIO, voice_ai_handler)
    )
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    app.add_error_handler(error_handler)
    setup_scheduler(app)

    threading.Thread(target=run_flask, daemon=True).start()

    def _on_signal(signum, frame):
        logger.warning(f"Signal {signum} received")
        _do_shutdown_backup(f"signal:{signum}")
        # درخواست توقف polling
        try:
            import asyncio
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(app.stop())
        except Exception:
            pass

    try:
        signal.signal(signal.SIGTERM, _on_signal)
        signal.signal(signal.SIGINT, _on_signal)
    except Exception as e:
        logger.warning(f"signal setup: {e}")

    logger.info("✅ Bot ready (sync shutdown backup to admin)")
    try:
        app.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)
    finally:
        # اگر بدون سیگنال هم تمام شد
        _do_shutdown_backup("finally")


if __name__ == "__main__":
    main()

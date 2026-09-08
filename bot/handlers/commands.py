from telegram import Update
from bot.handlers.middleware import check_and_rate_limit, start_rate_limit
from telegram.ext import ContextTypes
from bot.database import (
    save_user,
    get_all_users,
    get_user_city,
    update_user_field,
    set_last_main_msg_id,
)
from bot.utils.texts import get_text
from bot.utils.helpers import (
    build_message,
    get_main_keyboard,
    get_refresh_button,
    get_language_keyboard,
    get_calendar_buttons,
    get_calendar_text,
)
from bot.config import config
from bot.logger import logger
from bot.db_persist import send_db_to_admins, restore_db_from_file
import asyncio
from pathlib import Path
import secrets


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await start_rate_limit(update, context):
        return
    user = update.effective_user
    user_id = user.id
    first_name = user.first_name or "کاربر"
    save_user(user_id, first_name)
    city = get_user_city(user_id)
    message = await build_message(user_id, first_name, city)
    await update.message.reply_text("⬇️", reply_markup=get_main_keyboard(user_id))
    msg = await update.message.reply_text(message, reply_markup=get_refresh_button())
    context.user_data["last_main_msg_id"] = msg.message_id
    set_last_main_msg_id(user_id, msg.message_id)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_and_rate_limit(update, context):
        return
    user_id = update.effective_user.id
    await update.message.reply_text(get_text(user_id, "help"), reply_markup=get_main_keyboard(user_id))


async def city_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_and_rate_limit(update, context):
        return
    user_id = update.effective_user.id
    args = context.args
    if not args:
        await update.message.reply_text("❌ لطفاً نام شهر را وارد کن. مثال: `/city مشهد`")
        return
    new_city = " ".join(args)
    update_user_field(user_id, "city", new_city)
    await update.message.reply_text(
        get_text(user_id, "city_changed", city=new_city),
        reply_markup=get_main_keyboard(user_id)
    )


async def language_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_and_rate_limit(update, context):
        return
    await update.message.reply_text(
        "🌍 زبان خود را انتخاب کنید:",
        reply_markup=get_language_keyboard()
    )


async def calendar_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_and_rate_limit(update, context):
        return
    user_id = update.effective_user.id
    from bot.api.calendar import get_today_tehran
    today = get_today_tehran()
    text = get_calendar_text(today.year, today.month, today.day, user_id)
    await update.message.reply_text(
        text,
        reply_markup=get_calendar_buttons(today.year, today.month, today.day, user_id)
    )




async def automation_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Opt-in control for the proactive daily digest."""
    if not await check_and_rate_limit(update, context):
        return
    from bot.database import get_automation_preferences, set_daily_digest
    user_id = update.effective_user.id
    pref = get_automation_preferences(user_id)
    if not context.args:
        state = "روشن ✅" if pref["daily_digest"] else "خاموش ⛔"
        hour = getattr(config, "AUTOMATION_DIGEST_HOUR", 8)
        await update.message.reply_text(
            f"🤖 دستیار خودکار\n\nخلاصه روزانه: {state}\n"
            f"زمان ارسال: حدود ساعت {hour:02d}:00 به وقت تنظیم‌شده ربات.\n\n"
            "فعال‌سازی: /automation on\nخاموش‌کردن: /automation off"
        )
        return
    action = context.args[0].strip().lower()
    if action in ("on", "enable", "1", "روشن", "فعال"):
        set_daily_digest(user_id, True)
        await update.message.reply_text("✅ خلاصه روزانه فعال شد. حداکثر یک پیام در روز دریافت می‌کنی.")
    elif action in ("off", "disable", "0", "خاموش", "غیرفعال"):
        set_daily_digest(user_id, False)
        await update.message.reply_text("⛔ خلاصه روزانه خاموش شد و پیام خودکار دیگری ارسال نمی‌شود.")
    else:
        await update.message.reply_text("❌ فقط `on` یا `off` را وارد کن. مثال: /automation on")


async def memory_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """User-controlled view/clear for long-term AI memory."""
    if not await check_and_rate_limit(update, context):
        return
    from bot.database import get_ai_memory, delete_ai_memory, clear_ai_history_summary
    user_id = update.effective_user.id
    action = (context.args[0].strip().lower() if context.args else "status")
    if action in ("clear", "delete", "پاک", "حذف"):
        delete_ai_memory(user_id)
        clear_ai_history_summary(user_id)
        await update.message.reply_text("🧹 حافظه بلندمدت و خلاصه گفتگوهای قبلی پاک شد.")
        return
    mem = get_ai_memory(user_id, limit=20)
    if not mem:
        await update.message.reply_text("🧠 حافظه ذخیره‌شده‌ای برای حساب شما وجود ندارد.")
        return
    lines = ["🧠 حافظه ذخیره‌شده:", ""]
    for key, value in mem:
        lines.append(f"• {key}: {value[:180]}")
    lines += ["", "برای پاک‌کردن: /memory clear"]
    await update.message.reply_text("\n".join(lines)[:3900])


async def knowledge_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Search the bot's safe internal documentation."""
    if not await check_and_rate_limit(update, context):
        return
    query = " ".join(context.args).strip()
    if not query:
        await update.message.reply_text("📚 عبارت جستجو را وارد کن. مثال: /knowledge تنظیمات AI")
        return
    from bot.services.knowledge_base import format_knowledge_results
    await update.message.reply_text(format_knowledge_results(query))


async def agent_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Run the bounded autonomous planner for an explicit user goal."""
    if not await check_and_rate_limit(update, context):
        return
    args = list(context.args)
    if args and args[0].lower() in {"memory", "یادگیری", "learning"}:
        from bot.database import get_agent_learning
        rows = get_agent_learning(update.effective_user.id, limit=12)
        if not rows:
            await update.message.reply_text("🧠 هنوز داده‌ای از عملکرد Agent ذخیره نشده است.")
            return
        lines = ["🧠 حافظه عملکرد Agent", "", "این بخش فقط آمار موفقیت/شکست ابزارها را نشان می‌دهد.", ""]
        for agent, tool, ok, fail, err, updated in rows:
            total = int(ok or 0) + int(fail or 0)
            score = (100 * int(ok or 0) / total) if total else 0
            lines.append(f"• {agent}/{tool}: {score:.0f}% موفقیت ({total} اجرا)")
        await update.message.reply_text("\n".join(lines)[:3800])
        return
    goal = " ".join(args).strip()
    if not goal:
        await update.message.reply_text(
            "🤖 هدف را بنویس. مثال: /agent وضعیت هوا و بازار را بررسی کن\n🧠 /agent memory — آمار یادگیری Agent"
        )
        return
    from bot.services.multi_agent import run_multi_agent
    user_id = update.effective_user.id
    result = await run_multi_agent(goal, user_id=user_id)
    await update.message.reply_text(result[:3800])


async def plugins_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show plugin boundaries/status to administrators."""
    if not await check_and_rate_limit(update, context):
        return
    user_id = update.effective_user.id
    if user_id not in config.ADMIN_IDS:
        await update.message.reply_text(get_text(user_id, "admin_only"))
        return
    from bot.plugins import list_plugins, register_builtin_plugins
    register_builtin_plugins()
    lines = ["🔌 Plugin Registry", ""]
    for item in list_plugins():
        state = "فعال" if item["enabled"] else "غیرفعال"
        loaded = "loaded" if item["loaded"] else "not-loaded"
        lines.append(f"• {item['name']} — {state} — {loaded}")
        lines.append(f"  {item['description']}")
        if item["error"]:
            lines.append(f"  ⚠️ {item['error']}")
    await update.message.reply_text("\n".join(lines)[:3900])


async def diagnostics_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """نمایش سلامت داخلی AI/Tools/HTTP برای ادمین؛ بدون افشای API key."""
    if not await check_and_rate_limit(update, context):
        return
    user_id = update.effective_user.id
    if user_id not in config.ADMIN_IDS:
        await update.message.reply_text(get_text(user_id, "admin_only"))
        return
    from bot.utils.observability import snapshot
    from bot.services.ai_service import _PROVIDER_HEALTH
    data = snapshot()
    lines = ["🩺 Diagnostics", ""]
    for provider, h in sorted(_PROVIDER_HEALTH.items()):
        cooldown = max(0, int(h.get("cooldown_until", 0) - __import__("time").time()))
        lines.append(f"AI {provider}: ok={int(h['ok'])} fail={int(h['fail'])} cooldown={cooldown}s")
    for key, info in sorted(data["latency"].items()):
        lines.append(f"{key}: avg={info['avg_ms']}ms p95={info['p95_ms']}ms n={info['count']}")
    if len(lines) == 2:
        lines.append("هنوز متریک قابل توجهی ثبت نشده است.")
    await update.message.reply_text("\n".join(lines)[-3900:])


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_and_rate_limit(update, context):
        return
    user_id = update.effective_user.id
    if user_id not in config.ADMIN_IDS:
        await update.message.reply_text(get_text(user_id, "admin_only"))
        return
    from bot.database import get_db_connection
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users")
    total = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM users WHERE subscribed = 1")
    active = c.fetchone()[0]
    conn.close()
    await update.message.reply_text(get_text(user_id, "stats", total=total, active=active))


async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
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


# ─── بکاپ / ریستور رایگان (بدون دیسک پولی) ───────────────────

async def backup_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ادمین: /backup → فایل دیتابیس را در تلگرام می‌گیرد"""
    user_id = update.effective_user.id
    if user_id not in config.ADMIN_IDS:
        await update.message.reply_text("⛔ فقط ادمین")
        return
    await update.message.reply_text("⏳ در حال آماده‌سازی بکاپ...")
    ok, msg = await send_db_to_admins(context.bot)
    await update.message.reply_text("✅ " + msg if ok else "❌ " + msg)


async def restore_document_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin-only, validated database restore from a Telegram document."""
    user_id = update.effective_user.id if update.effective_user else None
    if user_id not in config.ADMIN_IDS:
        return

    msg = update.message
    if not msg or not msg.document:
        return

    caption = (msg.caption or "").strip().lower()
    if "/restore" not in caption and "restore" not in caption and "ریستور" not in caption:
        return

    doc = msg.document
    name = (doc.file_name or "").lower()
    allowed_ext = (".db", ".sqlite", ".sqlite3")
    if not name.endswith(allowed_ext) and "backup" not in name:
        await msg.reply_text("❌ فایل باید دیتابیس باشد (.db)")
        return

    max_bytes = max(1024 * 1024, int(getattr(config, "RESTORE_MAX_BYTES", 256 * 1024 * 1024)))
    declared_size = int(getattr(doc, "file_size", 0) or 0)
    if declared_size and declared_size > max_bytes:
        await msg.reply_text("❌ حجم فایل بکاپ بیش از حد مجاز است.")
        return

    await msg.reply_text("⏳ در حال بررسی و بازگردانی دیتابیس...")
    tmp = Path("/tmp") / f"restore_{user_id}_{secrets.token_hex(8)}.db"
    try:
        tg_file = await doc.get_file()
        await tg_file.download_to_drive(custom_path=str(tmp))
        if not tmp.exists() or tmp.stat().st_size < 100:
            await msg.reply_text("❌ فایل بکاپ نامعتبر یا خالی است.")
            return
        if tmp.stat().st_size > max_bytes:
            await msg.reply_text("❌ حجم فایل بکاپ بیش از حد مجاز است.")
            return
        ok, text = await restore_db_from_file(str(tmp))
        await msg.reply_text(text if ok else "❌ " + text)
    except Exception:
        logger.exception("restore error for admin %s", user_id)
        await msg.reply_text("❌ بازگردانی انجام نشد؛ فایل بکاپ را بررسی کنید.")
    finally:
        try:
            tmp.unlink(missing_ok=True)
        except Exception:
            pass


"""Feature-specific text handlers extracted from the Telegram message router.

Kept intentionally dependency-light and imported by ``messages.py`` as a
compatibility facade.
"""
import re
from bot.database import set_birth_date
from bot.utils.helpers import (
    get_date_tools_keyboard, get_tools_keyboard, get_market_keyboard,
    get_profile_keyboard, get_font_keyboard,
)
from bot.features.date.date_tools import (
    parse_shamsi, parse_any_date, parse_two_dates, parse_countdown,
    birthday_countdown, zodiac_animal, lunar_age, date_diff, age_diff,
    convert_with_weekday, search_events, custom_countdown,
)
from bot.features.date.converters import calculate_age, parse_birth_datetime
from bot.features.market.finance import (
    profit_loss, parse_profit, analyze_crypto, get_crypto_chart,
    get_crypto_analysis_keyboard, register_price_alert, calc_position_size,
)
from bot.features.tools.app_tools import calculator, world_distance, count_text, parse_two_places
from bot.features.fonts import apply_font, apply_all_fonts

async def _h_date_convert(u, c, t, uid):
    c.user_data.pop("waiting_for", None)
    p = parse_any_date(t)
    await u.message.reply_text(convert_with_weekday(*p) if p else "❌ نامعتبر", reply_markup=get_date_tools_keyboard())

async def _h_age_calc(u, c, t, uid):
    c.user_data.pop("waiting_for", None)
    p = parse_birth_datetime(t)
    await u.message.reply_text(calculate_age(*p) if p else "❌ نامعتبر", reply_markup=get_date_tools_keyboard())

async def _h_birthday(u, c, t, uid):
    c.user_data.pop("waiting_for", None)
    p = parse_shamsi(t)
    if p:
        y, m, d = p[0], p[1], p[2]; set_birth_date(uid, f"{y}/{m}/{d}")
        await u.message.reply_text(birthday_countdown(y, m, d), reply_markup=get_date_tools_keyboard())
    else:
        await u.message.reply_text("❌ نامعتبر", reply_markup=get_date_tools_keyboard())

async def _h_zodiac(u, c, t, uid):
    c.user_data.pop("waiting_for", None)
    p = parse_shamsi(t)
    await u.message.reply_text(zodiac_animal(p[0], p[1], p[2]) if p else "❌", reply_markup=get_date_tools_keyboard())

async def _h_lunar(u, c, t, uid):
    c.user_data.pop("waiting_for", None)
    p = parse_shamsi(t)
    await u.message.reply_text(lunar_age(p[0], p[1], p[2]) if p else "❌", reply_markup=get_date_tools_keyboard())

async def _h_date_diff(u, c, t, uid):
    c.user_data.pop("waiting_for", None)
    p = parse_two_dates(t)
    await u.message.reply_text(date_diff(*p[0], *p[1]) if p else "❌", reply_markup=get_date_tools_keyboard())

async def _h_age_diff(u, c, t, uid):
    c.user_data.pop("waiting_for", None)
    p = parse_two_dates(t)
    await u.message.reply_text(age_diff(*p[0], *p[1]) if p else "❌", reply_markup=get_date_tools_keyboard())

async def _h_event_search(u, c, t, uid):
    c.user_data.pop("waiting_for", None)
    await u.message.reply_text(search_events(t), reply_markup=get_date_tools_keyboard())

async def _h_countdown(u, c, t, uid):
    c.user_data.pop("waiting_for", None)
    p = parse_countdown(t)
    await u.message.reply_text(custom_countdown(*p) if p else "❌", reply_markup=get_date_tools_keyboard())

async def _h_calc(u, c, t, uid):
    c.user_data.pop("waiting_for", None)
    await u.message.reply_text(calculator(t), reply_markup=get_tools_keyboard())


async def _h_profit(u, c, t, uid):
    c.user_data.pop("waiting_for", None)
    p = parse_profit(t)
    await u.message.reply_text(profit_loss(*p) if p else "❌", reply_markup=get_market_keyboard())

async def _h_currency(u, c, t, uid):
    c.user_data.pop("waiting_for", None)
    from bot.features.market.finance import parse_currency_input, SYMBOL_TO_ID, convert_currency as smart_convert
    parsed = parse_currency_input(t)
    if not parsed:
        await u.message.reply_text(
            "❌ مثال:\n"
            "• `20 ton` یا `۱.۵ بیتکوین`\n"
            "• `100 دلار` یا `۵۰ تتر`\n"
            "• `50000 تومان دلار`\n"
            "• `1 btc eth`\n"
            "• `100 usdt toman`",
            reply_markup=get_market_keyboard(),
        )
        return
    amount, a, b = parsed
    try:
        result = await smart_convert(amount, a or "usd", b or "")
        await u.message.reply_text(result, reply_markup=get_market_keyboard())
    except Exception as e:
        await u.message.reply_text(f"⚠️ خطا در تبدیل: {e}", reply_markup=get_market_keyboard())


async def _h_crypto_full(u, c, t, uid):
    """تحلیل کامل + منوی دکمه‌ای زیرش (مثل Algo Analyzer)"""
    c.user_data.pop("waiting_for", None)
    raw = (t or "").strip().translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789"))
    parts = [p for p in raw.replace(",", " ").split() if p]
    symbol = ""
    days = 30
    for p in parts:
        pl = p.lower()
        if pl.replace(".", "", 1).isdigit():
            try:
                days = max(1, min(365, int(float(p))))
            except Exception:
                pass
        elif pl not in ("روز", "day", "days", "نمودار", "chart", "تحلیل", "analyze", "ارز"):
            if not symbol:
                symbol = p
    if not symbol and parts:
        symbol = parts[0]
    if not symbol:
        await u.message.reply_text(
            "❌ نماد را بفرستید. مثال: `btc` یا `eth 30`",
            reply_markup=get_market_keyboard(),
        )
        return

    symbol = symbol.lower().replace("usdt", "").strip()
    c.user_data["crypto_symbol"] = symbol
    wait = await u.message.reply_text(f"⏳ تحلیل {symbol.upper()}...")

    report = ""
    png = None
    try:
        import asyncio as _aio
        from bot.utils.task_manager import spawn
        chart_task = spawn(get_crypto_chart(symbol, days), name=f"crypto-chart-{symbol}")
        try:
            base = await analyze_crypto(symbol, ai_summary="", ai_guide="")
            ai_summary = ""
            ai_guide = ""
            try:
                from bot.services.ai_service import ask_ai
                prompt = (
                    "تو تحلیل‌گر حرفه‌ای بازار کریپتو هستی. همه داده‌های زیر را بخوان و دقیقاً با این قالب جواب بده:\n"
                    "جمع‌بندی: (۲ تا ۴ جمله فارسی؛ روند تایم‌فریم، پولبک/شکست، مومنتوم، سیگنال)\n"
                    "راهنما: (۱ تا ۲ جمله؛ آیا ورود الان به‌صرفه است یا فرصت گذشته یا صبر)\n\n"
                    "قوانین: بدون بولت اضافه، بدون عنوان انگلیسی، توصیه تضمینی نده.\n\n"
                    + base[:3200]
                )
                answer, _ = await ask_ai(uid, prompt)
                raw = (answer or "").strip()
                if "راهنما:" in raw:
                    a, b = raw.split("راهنما:", 1)
                    ai_summary = a.replace("جمع‌بندی:", "").strip().replace("\n", " ")
                    ai_guide = b.strip().replace("\n", " ")
                elif "جمع‌بندی:" in raw:
                    ai_summary = raw.split("جمع‌بندی:", 1)[-1].strip().replace("\n", " ")
                else:
                    ai_summary = raw.replace("\n", " ")
                if len(ai_summary) > 340:
                    ai_summary = ai_summary[:340].rsplit(" ", 1)[0] + "…"
                if len(ai_guide) > 240:
                    ai_guide = ai_guide[:240].rsplit(" ", 1)[0] + "…"
            except Exception:
                pass
            report = (
                await analyze_crypto(symbol, ai_summary=ai_summary, ai_guide=ai_guide)
                if (ai_summary or ai_guide)
                else base
            )
        except Exception as e:
            report = f"⚠️ خطا در تحلیل: {e}"
        try:
            png, _ = await chart_task
        except Exception:
            png = None
    except Exception as e:
        report = f"⚠️ خطا: {e}"

    try:
        await wait.delete()
    except Exception:
        pass

    menu = get_crypto_analysis_keyboard(symbol)
    # یک پیام واحد (عکس+تحلیل+منو) تا دکمه‌ها همان را ویرایش کنند
    body = (report or "❌ داده نبود.")
    if png:
        try:
            from io import BytesIO
            bio = BytesIO(png)
            bio.name = f"{symbol}_analysis.png"
            await u.message.reply_photo(
                photo=bio,
                caption=body[:1024],
                reply_markup=menu,
            )
        except Exception as e:
            await u.message.reply_text(body[:4000] + f"\n⚠️ نمودار: {e}", reply_markup=menu)
    else:
        await u.message.reply_text(body[:4000], reply_markup=menu)


async def _h_crypto_pos(u, c, t, uid):
    """پاسخ به ورودی سایز پوزیشن یا قیمت هشدار"""
    mode = c.user_data.pop("waiting_for", None)
    sym = c.user_data.get("crypto_symbol") or "btc"
    if mode == "crypto_pos":
        await u.message.reply_text(calc_position_size(t), reply_markup=get_crypto_analysis_keyboard(sym))
        return
    if mode == "crypto_alert":
        raw = (t or "").translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789"))
        nums = re.findall(r"[\d]+(?:\.\d+)?", raw)
        if not nums:
            await u.message.reply_text("❌ قیمت معتبر بفرستید. مثال: 64000")
            c.user_data["waiting_for"] = "crypto_alert"
            return
        price = float(nums[0])
        msg = await register_price_alert(uid, sym, price)
        await u.message.reply_text(msg, reply_markup=get_crypto_analysis_keyboard(sym))
        return


async def _h_crypto_chart(u, c, t, uid):
    return await _h_crypto_full(u, c, t, uid)


async def _h_crypto_analyze(u, c, t, uid):
    return await _h_crypto_full(u, c, t, uid)


async def _h_distance(u, c, t, uid):
    c.user_data.pop("waiting_for", None)
    from bot.features.tools.app_tools import parse_two_places
    parsed = parse_two_places(t)
    if not parsed:
        await u.message.reply_text(
            "❌ دو مکان بنویسید.\nمثال: تهران مشهد | تهران تا ترکیه | Paris to Tokyo",
            reply_markup=get_tools_keyboard(),
        )
        return
    p1, p2 = parsed
    await u.message.reply_text(await world_distance(p1, p2), reply_markup=get_tools_keyboard())




async def _h_birth_save(u, c, t, uid):
    c.user_data.pop("waiting_for", None)
    p = parse_shamsi(t)
    if p:
        set_birth_date(uid, f"{p[0]}/{p[1]}/{p[2]}")
        await u.message.reply_text(f"✅ ذخیره شد: {p[0]}/{p[1]}/{p[2]}", reply_markup=get_profile_keyboard())
    else:
        await u.message.reply_text("❌", reply_markup=get_profile_keyboard())

async def _h_count_text(u, c, t, uid):
    c.user_data.pop("waiting_for", None)
    await u.message.reply_text(count_text(t), reply_markup=get_tools_keyboard())


async def _h_font_text(u, c, t, uid):
    c.user_data.pop("waiting_for", None)
    font = c.user_data.get("selected_font", "bold")
    await u.message.reply_text(apply_font(t, font), reply_markup=get_font_keyboard())


async def _h_font_all(u, c, t, uid):
    c.user_data.pop("waiting_for", None)
    await u.message.reply_text(apply_all_fonts(t), reply_markup=get_font_keyboard())



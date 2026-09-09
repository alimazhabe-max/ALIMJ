"""Domain-specific Telegram handlers. Compatibility-preserving extraction from feature_handlers."""
from __future__ import annotations
import re
from bot.utils.helpers import get_market_keyboard
from bot.features.market.finance import profit_loss, parse_profit, analyze_crypto, get_crypto_chart, get_crypto_analysis_keyboard, register_price_alert, calc_position_size

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

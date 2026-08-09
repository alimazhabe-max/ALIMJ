"""هندلر پیام‌ها — همه قابلیت‌ها"""
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import ContextTypes
from bot.database import (
    update_user_field, get_user_city, set_last_main_msg_id,
    add_note, get_notes, add_reminder, track_usage,
    get_user_usage, set_birth_date, get_birth_date, get_user,
)
from bot.utils.helpers import (
    build_message, get_main_keyboard, get_refresh_button,
    get_country_keyboard, get_iran_cities_keyboard, get_iraq_cities_keyboard,
    get_language_keyboard, get_more_keyboard, get_date_tools_keyboard,
    get_religious_keyboard, get_market_keyboard, get_weather_geo_keyboard,
    get_tools_keyboard, get_fun_keyboard, get_profile_keyboard,
    get_calendar_text, get_calendar_buttons, ALL_CITIES, CITY_COUNTRY,
)
from bot.api.calendar import get_today_tehran
from bot.handlers.middleware import check_and_rate_limit
from bot.utils.motivation import get_motivation
from bot.features.date.date_tools import (
    parse_shamsi, parse_any_date, parse_two_dates, parse_countdown,
    birthday_countdown, zodiac_animal, lunar_age, date_diff, age_diff,
    convert_with_weekday, month_calendar, search_events, nowruz_countdown,
    world_clock, custom_countdown,
)
from bot.features.date.converters import calculate_age, parse_birth_datetime
from bot.features.religious import qibla_direction, daily_adhkar, daily_verse_hadith, religious_countdown, istikhara, istikhara_intro
from bot.features.market.finance import full_market_prices, convert_currency, profit_loss, parse_profit, get_top_crypto, convert_crypto
from bot.features.tools.app_tools import convert_unit, parse_unit, calculator, generate_password, count_text, bmi_calc, parse_bmi
from bot.features.fun.fun_tools import hafez_fal, truth_or_dare, joke_of_day, fact_of_day, daily_challenge
from bot.features.weather.weather_extra import weather_forecast, air_quality, city_distance
from bot.features.fonts import apply_font, list_fonts, get_font_preview
from bot.features.profile import profile_text
from bot.utils.helpers import get_font_keyboard
import re
from datetime import datetime, timedelta
import pytz
from bot.config import config


async def _send_main(update, context, text, user_id):
    context.user_data.pop("waiting_for", None)
    await update.message.reply_text("🏠 منوی اصلی", reply_markup=get_main_keyboard())
    msg = await update.message.reply_text(text, reply_markup=get_refresh_button())
    context.user_data["last_main_msg_id"] = msg.message_id
    set_last_main_msg_id(user_id, msg.message_id)
    return msg


def _is_back(text):
    t = text.strip()
    return t in ("🔙 بازگشت", "بازگشت") or "بازگشت" in t


def _is_back_more(text):
    return "بازگشت به بیشتر" in text


async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    if not await check_and_rate_limit(update, context):
        return

    text = update.message.text.strip()
    user_id = update.effective_user.id
    first_name = update.effective_user.first_name or "کاربر"
    city = get_user_city(user_id)
    waiting = context.user_data.get("waiting_for")

    if waiting:
        if _is_back(text) or _is_back_more(text):
            context.user_data.pop("waiting_for", None)
            await update.message.reply_text("➕ منوی بیشتر:", reply_markup=get_more_keyboard())
            return
        handlers = {
            "date_convert": _h_date_convert, "age_calc": _h_age_calc,
            "birthday": _h_birthday, "zodiac": _h_zodiac, "lunar": _h_lunar,
            "date_diff": _h_date_diff, "age_diff": _h_age_diff,
            "event_search": _h_event_search, "countdown": _h_countdown,
            "unit": _h_unit, "calc": _h_calc, "bmi": _h_bmi,
            "profit": _h_profit, "currency": _h_currency, "distance": _h_distance,
            "note": _h_note, "reminder": _h_reminder, "birth_save": _h_birth_save,
            "count_text": _h_count_text,
            "font_text": _h_font_text,
        }
        fn = handlers.get(waiting)
        if fn:
            await fn(update, context, text, user_id)
            return

    if text in ("🏙 انتخاب شهر", "انتخاب شهر"):
        await update.message.reply_text("🏙 کشور:", reply_markup=get_country_keyboard()); return
    if text in ("📅 تقویم", "تقویم"):
        t = get_today_tehran()
        await update.message.reply_text(get_calendar_text(t.year, t.month, t.day, user_id), reply_markup=get_calendar_buttons(t.year, t.month, t.day, user_id)); return
    if text in ("🌍 زبان", "زبان"):
        await update.message.reply_text("🌍 زبان:", reply_markup=get_language_keyboard()); return
    if text in ("➕ بیشتر", "بیشتر"):
        await update.message.reply_text("➕ بخش را انتخاب کنید:", reply_markup=get_more_keyboard()); return

    if text == "📅 تاریخ و سن":
        await update.message.reply_text("📅 تاریخ و سن:", reply_markup=get_date_tools_keyboard()); return
    if text == "🕌 مذهبی":
        await update.message.reply_text("🕌 مذهبی:", reply_markup=get_religious_keyboard()); return
    if text == "💰 بازار":
        await update.message.reply_text("💰 بازار:", reply_markup=get_market_keyboard()); return
    if text == "🌤 هوا و مکان":
        await update.message.reply_text("🌤 هوا و مکان:", reply_markup=get_weather_geo_keyboard()); return
    if text == "🛠 ابزارها":
        await update.message.reply_text("🛠 ابزارها:", reply_markup=get_tools_keyboard()); return
    if text == "🎮 سرگرمی":
        await update.message.reply_text("🎮 سرگرمی:", reply_markup=get_fun_keyboard()); return
    
    if text in ("🎨 فونت", "فونت"):
        await update.message.reply_text("🎨 فونت مورد نظر را انتخاب کنید یا لیست را ببینید:", reply_markup=get_font_keyboard()); return
    if text == "📋 لیست همه فونت‌ها":
        await update.message.reply_text(list_fonts(), reply_markup=get_font_keyboard()); return
    if text == "🎲 تصادفی":
        from bot.features.fonts.styles import FONT_NAMES
        import random
        key = random.choice(list(FONT_NAMES.keys()))
        context.user_data["selected_font"] = key
        context.user_data["waiting_for"] = "font_text"
        await update.message.reply_text(f"🎲 فونت تصادفی: `{key}`\nحالا متن خود را بفرستید:", reply_markup=get_font_keyboard()); return
    # انتخاب فونت از کیبورد
    from bot.features.fonts.styles import FONT_NAMES as _FN
    if text in _FN:
        context.user_data["selected_font"] = text
        context.user_data["waiting_for"] = "font_text"
        await update.message.reply_text(f"🎨 فونت `{text}` انتخاب شد.\nحالا متن فارسی یا انگلیسی خود را بفرستید:", reply_markup=get_font_keyboard()); return

    if text == "👤 پروفایل":
        await update.message.reply_text("👤 پروفایل:", reply_markup=get_profile_keyboard()); return
    if _is_back_more(text):
        await update.message.reply_text("➕ منوی بیشتر:", reply_markup=get_more_keyboard()); return

    # تاریخ و سن
    if text in ("🔄 مبدل تاریخ", "مبدل تاریخ"):
        context.user_data["waiting_for"] = "date_convert"; track_usage(user_id, "date_convert")
        await update.message.reply_text("🔄 تاریخ:\n`1403/05/18` یا `2024/08/09`", reply_markup=get_date_tools_keyboard()); return
    if text in ("🎂 محاسبه سن", "🎂 محاسبه سن دقیق", "محاسبه سن"):
        context.user_data["waiting_for"] = "age_calc"; track_usage(user_id, "age_calc")
        await update.message.reply_text("🎂 تولد شمسی:\n`1375/03/15`", reply_markup=get_date_tools_keyboard()); return
    if text in ("🎉 روزشمار تولد", "روزشمار تولد"):
        context.user_data["waiting_for"] = "birthday"; track_usage(user_id, "birthday")
        bd = get_birth_date(user_id)
        if bd and len(bd.split("/")) == 3:
            p = bd.split("/"); context.user_data.pop("waiting_for", None)
            await update.message.reply_text(birthday_countdown(int(p[0]), int(p[1]), int(p[2])), reply_markup=get_date_tools_keyboard()); return
        await update.message.reply_text("🎉 تولد شمسی:\n`1375/03/15`", reply_markup=get_date_tools_keyboard()); return
    if text in ("♈ برج و حیوان", "برج و حیوان"):
        context.user_data["waiting_for"] = "zodiac"; track_usage(user_id, "zodiac")
        await update.message.reply_text("♈ تولد شمسی:\n`1375/03/15`", reply_markup=get_date_tools_keyboard()); return
    if text in ("🌙 سن قمری", "سن قمری"):
        context.user_data["waiting_for"] = "lunar"; track_usage(user_id, "lunar")
        await update.message.reply_text("🌙 تولد شمسی:\n`1375/03/15`", reply_markup=get_date_tools_keyboard()); return
    if text in ("📆 اختلاف تاریخ", "📆 اختلاف دو تاریخ", "اختلاف تاریخ"):
        context.user_data["waiting_for"] = "date_diff"; track_usage(user_id, "date_diff")
        await update.message.reply_text("📆 دو تاریخ:\n`1375/03/15 1403/05/18`", reply_markup=get_date_tools_keyboard()); return
    if text in ("👥 اختلاف سن", "اختلاف سن"):
        context.user_data["waiting_for"] = "age_diff"; track_usage(user_id, "age_diff")
        await update.message.reply_text("👥 دو تولد:\n`1375/03/15 1380/06/20`", reply_markup=get_date_tools_keyboard()); return
    if text in ("📅 تقویم ماه", "تقویم ماه"):
        track_usage(user_id, "month_cal")
        await update.message.reply_text(month_calendar(), reply_markup=get_date_tools_keyboard()); return
    if text in ("🔍 مناسبت‌یاب", "مناسبت‌یاب"):
        context.user_data["waiting_for"] = "event_search"; track_usage(user_id, "event_search")
        await update.message.reply_text("🔍 کلمه کلیدی:\n`نوروز`", reply_markup=get_date_tools_keyboard()); return
    if text in ("🌸 شمارش نوروز", "شمارش نوروز"):
        track_usage(user_id, "nowruz")
        await update.message.reply_text(nowruz_countdown(), reply_markup=get_date_tools_keyboard()); return
    if text in ("🌍 ساعت جهانی", "ساعت جهانی"):
        track_usage(user_id, "world_clock")
        await update.message.reply_text(world_clock(), reply_markup=get_date_tools_keyboard()); return
    if text in ("⏳ شمارش‌معکوس", "شمارش‌معکوس"):
        context.user_data["waiting_for"] = "countdown"; track_usage(user_id, "countdown")
        await update.message.reply_text("⏳ تاریخ:\n`1405/01/01 نوروز`", reply_markup=get_date_tools_keyboard()); return

    # مذهبی
    if text in ("🕋 قبله‌نما", "قبله‌نما"):
        track_usage(user_id, "qibla")
        await update.message.reply_text(qibla_direction(city), reply_markup=get_religious_keyboard()); return
    if text in ("📿 اذکار روز", "اذکار روز"):
        track_usage(user_id, "adhkar")
        await update.message.reply_text(daily_adhkar(user_id), reply_markup=get_religious_keyboard()); return
    if text in ("📖 آیه و حدیث", "آیه و حدیث"):
        track_usage(user_id, "verse")
        await update.message.reply_text(await daily_verse_hadith(user_id), reply_markup=get_religious_keyboard()); return
    if text in ("🕌 مناسبت مذهبی", "مناسبت مذهبی"):
        track_usage(user_id, "rel_cd")
        await update.message.reply_text(religious_countdown(), reply_markup=get_religious_keyboard()); return
    
    if text in ("🙏 استخاره", "استخاره"):
        track_usage(user_id, "istikhara")
        context.user_data["waiting_for"] = "istikhara_confirm"
        await update.message.reply_text(istikhara_intro(), reply_markup=ReplyKeyboardMarkup(
            [[KeyboardButton("🙏 استخاره بگیر")], [KeyboardButton("🔙 بازگشت به مذهبی")]],
            resize_keyboard=True
        )); return
    if text == "🙏 استخاره بگیر":
        context.user_data.pop("waiting_for", None)
        track_usage(user_id, "istikhara_do")
        await update.message.reply_text(await istikhara(user_id), reply_markup=get_religious_keyboard()); return
    if text == "🔙 بازگشت به مذهبی":
        context.user_data.pop("waiting_for", None)
        await update.message.reply_text("🕌 مذهبی:", reply_markup=get_religious_keyboard()); return

    if text in ("🔔 تنظیم اذان", "تنظیم اذان"):
        track_usage(user_id, "azan")
        await update.message.reply_text(f"🔔 تنظیم اذان برای {city}\nفیلدهای دیتابیس آماده‌اند. اسکجولر نوتیف را جداگانه فعال کنید.", reply_markup=get_religious_keyboard()); return

    # بازار
    if text in ("💵 قیمت کامل بازار", "قیمت کامل بازار"):
        track_usage(user_id, "market")
        m = await update.message.reply_text("⏳ دریافت قیمت‌ها...")
        r = await full_market_prices()
        await m.edit_text(r)
        await update.message.reply_text("💰", reply_markup=get_market_keyboard()); return
    if text in ("💎 ۲۰ ارز برتر کریپتو", "۲۰ ارز برتر کریپتو", "کریپتو"):
        track_usage(user_id, "crypto_top")
        m = await update.message.reply_text("⏳ دریافت لیست کریپتو...")
        r = await get_top_crypto(20)
        await m.edit_text(r)
        await update.message.reply_text("💎", reply_markup=get_market_keyboard()); return
    if text in ("🔄 تبدیل ارز", "تبدیل ارز", "🔄 تبدیل ارز / کریپتو", "تبدیل ارز / کریپتو"):
        context.user_data["waiting_for"] = "currency"; track_usage(user_id, "currency")
        await update.message.reply_text(
            "🔄 مقدار و ارز را بفرست:\n\n"
            "• `100 دلار تومان`\n"
            "• `20 ton` یا `1.5 btc` یا `50 usdt`\n"
            "• `500000 ریال تومان`\n\n"
            "بیش از ۵۰۰ ارز دیجیتال پشتیبانی می‌شود.",
            reply_markup=get_market_keyboard()
        ); return
    if text in ("📈 سود و ضرر", "سود و ضرر"):
        context.user_data["waiting_for"] = "profit"; track_usage(user_id, "profit")
        await update.message.reply_text("📈 `1000 1200` یا `1000 1200 5`", reply_markup=get_market_keyboard()); return

    # هوا
    if text in ("🌤 پیش‌بینی هوا", "پیش‌بینی هوا"):
        track_usage(user_id, "forecast")
        await update.message.reply_text(await weather_forecast(city), reply_markup=get_weather_geo_keyboard()); return
    if text in ("🌫 کیفیت هوا", "کیفیت هوا"):
        track_usage(user_id, "aqi")
        await update.message.reply_text(await air_quality(city), reply_markup=get_weather_geo_keyboard()); return
    if text in ("🗺 فاصله شهرها", "فاصله شهرها"):
        context.user_data["waiting_for"] = "distance"; track_usage(user_id, "distance")
        await update.message.reply_text("🗺 `تهران مشهد`", reply_markup=get_weather_geo_keyboard()); return
    if text in ("📍 لوکیشن من", "لوکیشن من"):
        track_usage(user_id, "location")
        await update.message.reply_text(f"📍 لوکیشن را از 📎 بفرستید.\nشهر فعلی: {city}", reply_markup=get_weather_geo_keyboard()); return

    # ابزار
    if text in ("📐 تبدیل واحد", "تبدیل واحد"):
        context.user_data["waiting_for"] = "unit"; track_usage(user_id, "unit")
        await update.message.reply_text("📐 `10 km mile` یا `100 C F`", reply_markup=get_tools_keyboard()); return
    if text in ("🔢 ماشین‌حساب", "ماشین‌حساب"):
        context.user_data["waiting_for"] = "calc"; track_usage(user_id, "calc")
        await update.message.reply_text("🔢 `2+3*4`", reply_markup=get_tools_keyboard()); return
    if text in ("🔐 پسورد تصادفی", "پسورد تصادفی"):
        track_usage(user_id, "password")
        await update.message.reply_text(generate_password(12), reply_markup=get_tools_keyboard()); return
    if text in ("📝 شمارش متن", "شمارش متن"):
        context.user_data["waiting_for"] = "count_text"; track_usage(user_id, "count")
        await update.message.reply_text("📝 متن را بفرستید:", reply_markup=get_tools_keyboard()); return
    if text in ("⚖️ BMI", "BMI"):
        context.user_data["waiting_for"] = "bmi"; track_usage(user_id, "bmi")
        await update.message.reply_text("⚖️ `70 175`", reply_markup=get_tools_keyboard()); return
    if text in ("⏰ یادآوری", "یادآوری"):
        context.user_data["waiting_for"] = "reminder"; track_usage(user_id, "reminder")
        await update.message.reply_text("⏰ `30 متن یادآوری`", reply_markup=get_tools_keyboard()); return
    if text in ("📒 یادداشت", "یادداشت"):
        context.user_data["waiting_for"] = "note"; track_usage(user_id, "note")
        notes = get_notes(user_id, 5)
        msg = "📒 یادداشت‌ها:\n" + ("\n".join(f"• {n[1][:40]}" for n in notes) if notes else "خالی") + "\n\nمتن جدید:"
        await update.message.reply_text(msg, reply_markup=get_tools_keyboard()); return

    # سرگرمی
    if text in ("📖 فال حافظ", "فال حافظ"):
        track_usage(user_id, "hafez"); await update.message.reply_text(hafez_fal(user_id), reply_markup=get_fun_keyboard()); return
    
    if text in ("🎯 حقیقت یا جرات", "حقیقت یا جرات"):
        track_usage(user_id, "tod"); await update.message.reply_text(truth_or_dare(), reply_markup=get_fun_keyboard()); return
    if text in ("😂 جوک روز", "جوک روز"):
        track_usage(user_id, "joke"); await update.message.reply_text(joke_of_day(), reply_markup=get_fun_keyboard()); return
    if text in ("🧠 دانستنی روز", "دانستنی روز"):
        track_usage(user_id, "fact"); await update.message.reply_text(fact_of_day(), reply_markup=get_fun_keyboard()); return
    if text in ("💪 چالش امروز", "چالش امروز"):
        track_usage(user_id, "challenge"); await update.message.reply_text(daily_challenge(), reply_markup=get_fun_keyboard()); return
    if text in ("💖 جمله انگیزشی", "جمله انگیزشی"):
        track_usage(user_id, "motivation"); await update.message.reply_text(f"💖 {get_motivation()}", reply_markup=get_fun_keyboard()); return

    # پروفایل
    if text in ("👤 پروفایل من", "پروفایل من"):
        track_usage(user_id, "profile")
        await update.message.reply_text(profile_text(user_id, first_name), reply_markup=get_profile_keyboard(), parse_mode="Markdown"); return
    if text in ("📊 آمار من", "آمار من"):
        track_usage(user_id, "stats")
        usage = get_user_usage(user_id)
        msg = "📊 آمار:\n" + ("\n".join(f"• {f}: {c}" for f, c in usage[:15]) if usage else "خالی")
        await update.message.reply_text(msg, reply_markup=get_profile_keyboard()); return
    if text in ("🎂 ذخیره تاریخ تولد", "ذخیره تاریخ تولد"):
        context.user_data["waiting_for"] = "birth_save"
        await update.message.reply_text("🎂 `1375/03/15`", reply_markup=get_profile_keyboard()); return

    if text in ("🇮🇷 ایران", "ایران"):
        await update.message.reply_text("🇮🇷 شهر:", reply_markup=get_iran_cities_keyboard()); return
    if text in ("🇮🇶 عراق", "عراق"):
        await update.message.reply_text("🇮🇶 شهر:", reply_markup=get_iraq_cities_keyboard()); return
    if _is_back(text):
        await _send_main(update, context, await build_message(user_id, first_name, city), user_id); return
    if text.startswith("فارسی") or text == "فارسی 🇮🇷":
        update_user_field(user_id, "language", "fa"); await _send_main(update, context, await build_message(user_id, first_name, city), user_id); return
    if text.startswith("English") or text == "English 🇬🇧":
        update_user_field(user_id, "language", "en"); await _send_main(update, context, await build_message(user_id, first_name, city), user_id); return
    if "العربية" in text or "العربيه" in text:
        update_user_field(user_id, "language", "ar"); await _send_main(update, context, await build_message(user_id, first_name, city), user_id); return
    if text in ALL_CITIES:
        update_user_field(user_id, "city", text); update_user_field(user_id, "country", CITY_COUNTRY.get(text, "Iran"))
        await _send_main(update, context, f"✅ شهر → **{text}**\n\n" + await build_message(user_id, first_name, text), user_id); return


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

async def _h_unit(u, c, t, uid):
    c.user_data.pop("waiting_for", None)
    p = parse_unit(t)
    await u.message.reply_text(convert_unit(*p) if p else "❌", reply_markup=get_tools_keyboard())

async def _h_calc(u, c, t, uid):
    c.user_data.pop("waiting_for", None)
    await u.message.reply_text(calculator(t), reply_markup=get_tools_keyboard())

async def _h_bmi(u, c, t, uid):
    c.user_data.pop("waiting_for", None)
    p = parse_bmi(t)
    await u.message.reply_text(bmi_calc(*p) if p else "❌", reply_markup=get_tools_keyboard())

async def _h_profit(u, c, t, uid):
    c.user_data.pop("waiting_for", None)
    p = parse_profit(t)
    await u.message.reply_text(profit_loss(*p) if p else "❌", reply_markup=get_market_keyboard())

async def _h_currency(u, c, t, uid):
    c.user_data.pop("waiting_for", None)
    parts = t.split()
    try:
        amount = float(parts[0].translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")))
        if len(parts) >= 3:
            await u.message.reply_text(await convert_currency(amount, parts[1], parts[2]), reply_markup=get_market_keyboard()); return
        if len(parts) == 2:
            # کریپتو: 20 ton
            await u.message.reply_text(await convert_crypto(amount, parts[1]), reply_markup=get_market_keyboard()); return
    except Exception:
        pass
    await u.message.reply_text(
        "❌ مثال:\n`100 دلار تومان`\n`20 ton`\n`1.5 btc`",
        reply_markup=get_market_keyboard()
    )

async def _h_distance(u, c, t, uid):
    c.user_data.pop("waiting_for", None)
    parts = t.split()
    await u.message.reply_text(city_distance(parts[0], parts[1]) if len(parts) >= 2 else "❌", reply_markup=get_weather_geo_keyboard())

async def _h_note(u, c, t, uid):
    c.user_data.pop("waiting_for", None)
    add_note(uid, t)
    await u.message.reply_text("✅ ذخیره شد", reply_markup=get_tools_keyboard())

async def _h_reminder(u, c, t, uid):
    c.user_data.pop("waiting_for", None)
    m = re.match(r"^(\d+)\s+(.+)$", t.strip())
    if m:
        mins, msg = int(m.group(1)), m.group(2)
        at = (datetime.now(pytz.timezone(config.TIMEZONE)) + timedelta(minutes=mins)).strftime("%Y-%m-%d %H:%M:%S")
        add_reminder(uid, msg, at)
        await u.message.reply_text(f"✅ بعد از {mins} دقیقه", reply_markup=get_tools_keyboard())
    else:
        await u.message.reply_text("❌ `30 متن`", reply_markup=get_tools_keyboard())

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

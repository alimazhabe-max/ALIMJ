from bot.utils.city_data import IRAN_CITIES, IRAQ_CITIES, CITY_COUNTRY, ALL_CITIES
from bot.utils.keyboard_factory import (
    get_refresh_button, get_main_keyboard, get_ai_keyboard, get_ai_model_keyboard,
    get_more_keyboard, get_date_tools_keyboard, get_religious_keyboard, get_market_keyboard,
    get_weather_geo_keyboard, get_tools_keyboard, get_azan_keyboard, get_fun_keyboard,
    get_joke_keyboard, get_profile_keyboard, get_smart_settings_keyboard, get_country_keyboard,
    get_iran_cities_keyboard, get_iraq_cities_keyboard, get_language_keyboard,
    get_font_keyboard, get_font_en_keyboard, get_font_fa_keyboard,
)
from telegram import (
    InlineKeyboardButton, InlineKeyboardMarkup,
    KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove,
)
import jdatetime
import pytz
from datetime import datetime
from bot.config import config
from bot.api.calendar import get_today_tehran, get_hijri_date, get_shamsi_events, get_hijri_events
from bot.api.prayer import get_prayer_times, get_next_prayer_time, get_prayer_times_for_date
from bot.api.weather import get_weather, format_weather
from bot.api.tgju import get_market_prices
from bot.utils.texts import get_text
from bot.utils.motivation import get_motivation
from bot.database import get_user_city, get_user_country, get_user_language

PERSIAN_MONTHS = {
    1: "فروردین", 2: "اردیبهشت", 3: "خرداد", 4: "تیر",
    5: "مرداد", 6: "شهریور", 7: "مهر", 8: "آبان",
    9: "آذر", 10: "دی", 11: "بهمن", 12: "اسفند"
}
PERSIAN_WEEKDAYS = {
    0: "شنبه", 1: "یکشنبه", 2: "دوشنبه", 3: "سه‌شنبه",
    4: "چهارشنبه", 5: "پنجشنبه", 6: "جمعه"
}

def to_persian_num(num):
    mapping = {'0': '۰', '1': '۱', '2': '۲', '3': '۳', '4': '۴',
               '5': '۵', '6': '۶', '7': '۷', '8': '۸', '9': '۹'}
    return ''.join(mapping.get(ch, ch) for ch in str(num))





async def build_message(user_id, user_name, city):
    """ساخت پیام اصلی — کاملاً مقاوم؛ هیچ خطایی بیرون نمی‌رود."""
    import asyncio

    try:
        return await _build_message_inner(user_id, user_name, city)
    except Exception as e:
        try:
            from bot.logger import logger
            logger.error("build_message fatal: %s", e, exc_info=True)
        except Exception:
            pass
        name = str(user_name or "کاربر")
        return (
            f"🌟 سلام {name} عزیز!\n\n"
            f"⚠️ بارگذاری اطلاعات موقتاً ممکن نیست.\n"
            f"کد: {type(e).__name__}\n"
            f"/start را دوباره بفرستید."
        )


async def _build_message_inner(user_id, user_name, city):
    import asyncio

    nl = chr(10)
    city = city or "قم"
    # نام کاربر ممکن است { } داشته باشد و text.format را بشکند
    user_name = str(user_name or "کاربر").replace("{", "(").replace("}", ")")

    try:
        now = datetime.now(pytz.timezone(config.TIMEZONE))
        today = get_today_tehran()
    except Exception:
        now = datetime.now()
        today = jdatetime.date.today()

    try:
        weekday = PERSIAN_WEEKDAYS.get(today.weekday(), "")
        month_name = PERSIAN_MONTHS.get(today.month, "")
        year_p = to_persian_num(today.year)
        month_p = to_persian_num(f"{today.month:02d}")
        day_p = to_persian_num(f"{today.day:02d}")
        persian_date = f"{weekday} {to_persian_num(today.day)} {month_name} {year_p}/{month_p}/{day_p}"
        greg = today.togregorian()
        miladi_date = greg.strftime("%B %d, %A") + f" {greg.year}/{greg.month:02d}/{greg.day:02d}"
    except Exception:
        persian_date = "—"
        miladi_date = "—"
        greg = datetime.now().date()

    hijri_date = "—"
    hijri_events_text = "• —"
    try:
        hijri = get_hijri_date(greg) or {}
        hy = to_persian_num(hijri.get("year", 0))
        hm = to_persian_num(f"{int(hijri.get('month', 0) or 0):02d}")
        hd = to_persian_num(f"{int(hijri.get('day', 0) or 0):02d}")
        hijri_date = f"{to_persian_num(hijri.get('day', 0))} {hijri.get('month_name', '—')} {hy}/{hm}/{hd}"
        hijri_events_list = get_hijri_events(hijri.get("month", 0), hijri.get("day", 0)) or []
        hijri_events_text = chr(10).join([f"• {e}" for e in hijri_events_list]) or "• —"
    except Exception:
        pass

    hijri_tomorrow_text = "• —"
    shamsi_tomorrow_text = "• —"
    shamsi_text = "• —"
    try:
        tomorrow = today + jdatetime.timedelta(days=1)
        hijri_tomorrow = get_hijri_date(tomorrow.togregorian()) or {}
        hijri_tomorrow_events = get_hijri_events(
            hijri_tomorrow.get("month", 0), hijri_tomorrow.get("day", 0)
        ) or []
        hijri_tomorrow_text = chr(10).join([f"• {e}" for e in hijri_tomorrow_events]) or "• —"
        shamsi_tomorrow = get_shamsi_events(tomorrow.year, tomorrow.month, tomorrow.day) or []
        shamsi_tomorrow_text = chr(10).join([f"• {e}" for e in shamsi_tomorrow]) or "• —"
        shamsi_events_list = get_shamsi_events(today.year, today.month, today.day) or []
        shamsi_text = chr(10).join([f"• {e}" for e in shamsi_events_list]) or "• —"
    except Exception:
        pass

    country = "Iran"
    try:
        country = get_user_country(user_id) or "Iran"
    except Exception:
        pass

    # درخواست‌های blocking (requests) را در executor اجرا می‌کنیم
    # تا event loop بات هنگام بروزرسانی قفل نشود.
    loop = asyncio.get_running_loop()

    prayer_text = "⚠️ اوقات شرعی در دسترس نیست."
    next_prayer_text = ""
    try:
        prayer_times = await loop.run_in_executor(
            None, lambda: get_prayer_times(city, country=country)
        )
        if prayer_times:
            prayer_text = nl.join([f"🕌 {k}: {v}" for k, v in prayer_times.items()])
            try:
                result = get_next_prayer_time(prayer_times, now)
                if result and result[0]:
                    name, delta = result
                    total_sec = int(getattr(delta, "total_seconds", lambda: delta.seconds)())
                    hours = total_sec // 3600
                    minutes = (total_sec % 3600) // 60
                    seconds = total_sec % 60
                    next_prayer_text = (
                        nl
                        + f"⏳ تا {name}: {to_persian_num(hours)} ساعت و "
                        + f"{to_persian_num(minutes)} دقیقه و {to_persian_num(seconds)} ثانیه"
                        + nl
                    )
            except Exception:
                pass
    except Exception:
        pass

    weather_text = "⚠️ آب و هوا در دسترس نیست."
    try:
        weather = await loop.run_in_executor(None, lambda: get_weather(city))
        if weather:
            weather_text = (
                f"🌡️ دما: {weather.get('temp', '—')}°C"
                + nl
                + f"🌤️ وضعیت: {weather.get('condition', '—')}"
                + nl
                + f"💧 رطوبت: {weather.get('humidity', '—')}%"
            )
    except Exception:
        pass

    market_text = "⚠️ قیمت بازار در دسترس نیست." + nl
    try:
        market = await get_market_prices()
        dollar = market.get("dollar") if isinstance(market, dict) else None
        gold18 = market.get("gold18") if isinstance(market, dict) else None
        parts = []
        if isinstance(dollar, (int, float)):
            parts.append(f"💵 دلار: {to_persian_num(f'{int(dollar):,}')} ریال")
        if isinstance(gold18, (int, float)):
            parts.append(f"🥇 طلای ۱۸ عیار: {to_persian_num(f'{int(gold18):,}')} ریال")
        if parts:
            market_text = nl.join(parts) + nl
    except Exception:
        pass

    motivation = "—"
    try:
        motivation = get_motivation() or "—"
    except Exception:
        pass

    def _safe_text(key, **kwargs):
        try:
            return get_text(user_id, key, **kwargs)
        except Exception:
            return ""

    try:
        message = (
            _safe_text("welcome", name=user_name) + nl + nl
            + f"📅 امروز (شمسی): {persian_date}" + nl
            + f"📅 امروز (میلادی): {miladi_date}" + nl
            + f"🌙 امروز (قمری): {hijri_date}" + nl + nl
            + f"📌 مناسبت‌های قمری امروز:" + nl + hijri_events_text + nl + nl
            + f"📌 مناسبت‌های قمری فردا:" + nl + hijri_tomorrow_text + nl + nl
            + f"📌 مناسبت‌های شمسی امروز:" + nl + shamsi_text + nl + nl
            + f"🔮 مناسبت‌های شمسی فردا:" + nl + shamsi_tomorrow_text + nl + nl
            + _safe_text("prayer", city=city) + nl + prayer_text
            + next_prayer_text + nl
            + _safe_text("weather", city=city) + nl + weather_text + nl + nl
            + "📊 قیمت بازار:" + nl + market_text + nl
            + _safe_text("motivation") + nl + motivation + nl + nl
            + _safe_text("change_city")
        )
    except Exception:
        message = (
            f"🌟 سلام {user_name} عزیز!\n\n"
            f"⚠️ بخشی از اطلاعات موقتاً در دسترس نیست. /start را دوباره بفرستید."
        )

    if len(message) > 4000:
        message = message[:3990] + "\n…"
    return message

# ───────────────── فقط بروزرسانی زیر پیام (اینلاین) ─────────────────


# ───────────────── بقیه دکمه‌ها پایین صفحه ─────────────────


































# ───────────────── تقویم (اینلاین) ─────────────────

def get_calendar_buttons(year, month, day, user_id):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("◀️ روز قبل", callback_data=f"day_{year}_{month}_{day-1}"),
            InlineKeyboardButton("📅 امروز", callback_data="calendar_today"),
            InlineKeyboardButton("روز بعد ▶️", callback_data=f"day_{year}_{month}_{day+1}"),
        ],
        [
            InlineKeyboardButton("◀️ ماه قبل", callback_data=f"cal_{year}_{month-1}_{day}"),
            InlineKeyboardButton("ماه بعد ▶️", callback_data=f"cal_{year}_{month+1}_{day}"),
        ],
        [InlineKeyboardButton("🔙 بازگشت به منو", callback_data="back_to_main")],
    ])


def get_calendar_text(year, month, day, user_id):
    """متن تقویم برای روز انتخاب‌شده — مناسبت + اوقات شرعی همان روز + هوا همان روز"""
    try:
        import httpx
        from bot.features.weather.weather_extra import CITY_COORDS, WEATHER_CODES, _norm_city

        target = jdatetime.date(year, month, day)
        date_str = (
            f"{PERSIAN_WEEKDAYS[target.weekday()]} "
            f"{to_persian_num(target.day)} {PERSIAN_MONTHS[target.month]} "
            f"{to_persian_num(target.year)}"
        )
        shamsi = get_shamsi_events(year, month, day)
        shamsi_text = chr(10).join([f"• {e}" for e in shamsi]) if shamsi else "• هیچ مناسبت خاصی ثبت نشده است."

        hijri = get_hijri_date(target.togregorian())
        hijri_events_list = get_hijri_events(hijri['month'], hijri['day'])
        hijri_text = chr(10).join([f"• {e}" for e in hijri_events_list]) if hijri_events_list else "• هیچ مناسبت قمری خاصی ثبت نشده است."

        city = get_user_city(user_id) or "تهران"
        country = get_user_country(user_id) or "Iran"
        g = target.togregorian()
        # Aladhan: DD-MM-YYYY
        g_str = f"{g.day:02d}-{g.month:02d}-{g.year}"
        prayer = get_prayer_times_for_date(city, g_str, country=country)
        if prayer:
            prayer_text = chr(10).join([f"🕌 {k}: {v}" for k, v in prayer.items()])
        else:
            prayer_text = "⚠️ اوقات شرعی در دسترس نیست."


        # هوا: اول Open-Meteo حرفه‌ای ۷روزه از همان روز، بعد fallback
        weather_text = "⚠️ آب و هوا در دسترس نیست."
        try:
            from bot.features.weather.weather_extra import CITY_COORDS, WEATHER_CODES, _norm_city
            import requests as _req
            cname = _norm_city(city)
            coords = CITY_COORDS.get(cname) or CITY_COORDS.get("تهران")
            lat, lon = coords
            start = f"{g.year:04d}-{g.month:02d}-{g.day:02d}"
            from datetime import timedelta as _td
            end_d = g + _td(days=6)
            end = f"{end_d.year:04d}-{end_d.month:02d}-{end_d.day:02d}"
            params = {
                "latitude": lat,
                "longitude": lon,
                "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum,windspeed_10m_max",
                "timezone": "Asia/Tehran",
                "start_date": start,
                "end_date": end,
            }
            r = _req.get("https://api.open-meteo.com/v1/forecast", params=params, timeout=12)
            if r.status_code == 200:
                daily = r.json().get("daily", {})
                times = daily.get("time") or []
                tmax = daily.get("temperature_2m_max") or []
                tmin = daily.get("temperature_2m_min") or []
                codes = daily.get("weather_code") or daily.get("weathercode") or []
                wind = daily.get("windspeed_10m_max") or []
                precip = daily.get("precipitation_sum") or []
                names = ["روز۱", "روز۲", "روز۳", "روز۴", "روز۵", "روز۶", "روز۷"]
                lines = ["🌤 پیش‌بینی ۷روزه (از این تاریخ)"]
                for i in range(min(7, len(times))):
                    d = times[i][5:] if times[i] else ""
                    mx = tmax[i] if i < len(tmax) else "?"
                    mn = tmin[i] if i < len(tmin) else "?"
                    try:
                        code = int(codes[i]) if i < len(codes) else 0
                    except Exception:
                        code = 0
                    desc = WEATHER_CODES.get(code, "")
                    wd = wind[i] if i < len(wind) else "?"
                    lines.append(f"• {names[i]} ({d}): {to_persian_num(mn)}°~{to_persian_num(mx)}° {desc}")
                weather_text = chr(10).join(lines)
            else:
                weather = get_weather(city)
                if weather:
                    from bot.features.weather.weather import format_weather
                    weather_text = format_weather(city, weather)
        except Exception as e:
            from bot.logger import logger
            logger.error(f"calendar weather: {e}")
            weather = get_weather(city)
            if weather:
                from bot.features.weather.weather import format_weather
                weather_text = format_weather(city, weather)

        return (
            f"📅 {date_str}" + chr(10) +
            f"🌙 قمری: {to_persian_num(hijri['day'])} {hijri['month_name']} {to_persian_num(hijri['year'])}" + chr(10)*2 +
            f"📌 مناسبت‌های شمسی:" + chr(10) + shamsi_text + chr(10)*2 +
            f"📌 مناسبت‌های قمری:" + chr(10) + hijri_text + chr(10)*2 +
            f"⏰ اوقات شرعی ({city}) — همین روز" + chr(10) + prayer_text + chr(10)*2 +
            f"🌦️ آب و هوا (۷ روز از این تاریخ)" + chr(10) + weather_text + chr(10)*2 +
            "🔄 با دکمه‌های زیر روز یا ماه را تغییر دهید."
        )
    except Exception as e:
        from bot.logger import logger
        logger.error(f"get_calendar_text: {e}")
        return "❌ خطا در نمایش تقویم."









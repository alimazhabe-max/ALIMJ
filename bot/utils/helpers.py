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
from bot.api.weather import get_weather
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

    # زمان دقیق بروزرسانی — تضمین می‌کند متن پیام هر بار با قبلی فرق کند
    # تا تلگرام خطای Message is not modified ندهد.
    try:
        upd_h = to_persian_num(f"{now.hour:02d}")
        upd_m = to_persian_num(f"{now.minute:02d}")
        upd_s = to_persian_num(f"{now.second:02d}")
        updated_at = f"🔄 آخرین بروزرسانی: {upd_h}:{upd_m}:{upd_s}"
    except Exception:
        updated_at = "🔄 آخرین بروزرسانی: —"

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
            + _safe_text("change_city") + nl + nl
            + updated_at
        )
    except Exception:
        message = (
            f"🌟 سلام {user_name} عزیز!\n\n"
            f"⚠️ بخشی از اطلاعات موقتاً در دسترس نیست. /start را دوباره بفرستید.\n\n"
            f"{updated_at}"
        )

    if len(message) > 4000:
        message = message[:3990] + "\n…"
    return message

# ───────────────── شهرها ─────────────────
IRAN_CITIES = [
    "تهران", "مشهد", "اصفهان",
    "شیراز", "تبریز", "قم",
    "کرج", "اهواز", "کرمانشاه",
    "ارومیه", "رشت", "کرمان",
    "یزد", "همدان", "اردبیل",
    "زاهدان", "بندرعباس", "ساری",
    "قزوین", "خرم‌آباد", "سنندج",
    "بوشهر", "اراک", "زنجان",
    "گرگان", "سمنان", "بجنورد",
    "ایلام", "یاسوج", "بیرجند",
    "ساوه",
]

IRAQ_CITIES = [
    "نجف", "کربلا", "کاظمین",
    "سامرا", "بغداد",
]

CITY_COUNTRY = {city: "Iran" for city in IRAN_CITIES}
CITY_COUNTRY.update({city: "Iraq" for city in IRAQ_CITIES})
ALL_CITIES = set(IRAN_CITIES) | set(IRAQ_CITIES)

# ───────────────── فقط بروزرسانی زیر پیام (اینلاین) ─────────────────

def get_refresh_button():
    """فقط دکمه بروزرسانی زیر پیام"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 بروزرسانی", callback_data="refresh_main")]
    ])

# ───────────────── بقیه دکمه‌ها پایین صفحه ─────────────────

def get_main_keyboard():
    """کیبورد پایین — انتخاب شهر، تقویم، زبان، بیشتر"""
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("🏙 انتخاب شهر"), KeyboardButton("📅 تقویم")],
            [KeyboardButton("🌍 زبان"), KeyboardButton("➕ بیشتر")],
            [KeyboardButton("🤖 دستیار هوشمند")],
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
        input_field_placeholder="پیام بنویسید یا از دکمه‌ها استفاده کنید...",
    )


def get_ai_keyboard(user_id=None):
    """دکمه‌های شیشه‌ای زیر پیام AI: انتخاب ارائه‌دهنده و پاک‌کردن حافظه."""
    from bot.services.ai_service import get_selected_model, _PROVIDER_PRETTY
    selected = get_selected_model(user_id) if user_id is not None else None
    selected_text = "🎛 انتخاب مدل AI"
    if selected:
        provider = selected[0]
        pretty = _PROVIDER_PRETTY.get(provider, provider)
        selected_text = f"🎛 فعال: {pretty}"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(selected_text, callback_data="ai_models")],
        [InlineKeyboardButton("🧹 حذف حافظه", callback_data="ai_clear_memory")],
    ])


def get_ai_model_keyboard(user_id=None):
    """
    لیست ارائه‌دهنده‌ها (نه تک‌تک مدل‌ها).
    با انتخاب یک ارائه‌دهنده، همه مدل‌هایش به‌صورت خودکار امتحان می‌شوند.
    """
    from bot.services.ai_service import available_providers, get_selected_model
    selected = get_selected_model(user_id) if user_id is not None else None
    selected_provider = selected[0] if selected else None
    rows = []
    for index, (provider, label) in enumerate(available_providers()):
        mark = "✅ " if selected_provider == provider else ""
        rows.append([
            InlineKeyboardButton(
                f"{mark}{label}",
                callback_data=f"ai_provider:{index}",
            )
        ])
    if not rows:
        rows.append([InlineKeyboardButton("❌ هیچ سرویسی تنظیم نشده", callback_data="ai_noop")])
    rows.append([InlineKeyboardButton("↩️ برگشت", callback_data="ai_models_back")])
    return InlineKeyboardMarkup(rows)


def get_more_keyboard():
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("📅 تاریخ و سن"), KeyboardButton("🕌 مذهبی")],
            [KeyboardButton("💰 بازار"), KeyboardButton("🌤 هوا و مکان")],
            [KeyboardButton("🛠 ابزارها"), KeyboardButton("🎮 سرگرمی")],
            [KeyboardButton("🎨 فونت"), KeyboardButton("👤 پروفایل")],
            [KeyboardButton("🔙 بازگشت")],
        ],
        resize_keyboard=True,
    )


def get_date_tools_keyboard():
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("🔄 مبدل تاریخ"), KeyboardButton("🎂 محاسبه سن")],
            [KeyboardButton("🎉 روزشمار تولد"), KeyboardButton("♈ برج و حیوان")],
            [KeyboardButton("🌙 سن قمری"), KeyboardButton("📆 اختلاف تاریخ")],
            [KeyboardButton("👥 اختلاف سن"), KeyboardButton("📅 تقویم ماه")],
            [KeyboardButton("🔍 مناسبت‌یاب"), KeyboardButton("🌸 شمارش نوروز")],
            [KeyboardButton("🌍 ساعت جهانی"), KeyboardButton("⏳ شمارش‌معکوس")],
            [KeyboardButton("🔙 بازگشت به بیشتر")],
        ],
        resize_keyboard=True,
    )


def get_religious_keyboard():
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("🕋 قبله‌نما"), KeyboardButton("📿 اذکار روز")],
            [KeyboardButton("📖 آیه و حدیث"), KeyboardButton("🕌 مناسبت مذهبی")],
            [KeyboardButton("🙏 استخاره"), KeyboardButton("🔔 تنظیم اذان")],
            [KeyboardButton("🔙 بازگشت به بیشتر")],
        ],
        resize_keyboard=True,
    )


def get_market_keyboard():
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("💵 قیمت کامل بازار"), KeyboardButton("💎 ۲۰ ارز برتر کریپتو")],
            [KeyboardButton("🔄 تبدیل ارز / کریپتو"), KeyboardButton("📈 سود و ضرر")],
            [KeyboardButton("🔙 بازگشت به بیشتر")],
        ],
        resize_keyboard=True,
    )


def get_weather_geo_keyboard():
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("🌤 پیش‌بینی هوا"), KeyboardButton("🌫 کیفیت هوا")],
            [KeyboardButton("📍 لوکیشن من")],
            [KeyboardButton("🔙 بازگشت به بیشتر")],
        ],
        resize_keyboard=True,
    )


def get_tools_keyboard():
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("🔢 ماشین‌حساب"), KeyboardButton("🔐 پسورد تصادفی")],
            [KeyboardButton("📝 شمارش متن"), KeyboardButton("🗺 فاصله جهانی")],
            [KeyboardButton("🔙 بازگشت به بیشتر")],
        ],
        resize_keyboard=True,
    )


def get_azan_keyboard(settings: dict = None):
    """کیبورد تنظیم اذان با وضعیت فعلی هر نماز."""
    if not settings:
        settings = {
            "enabled": True,
            "fajr": True, "dhuhr": False, "asr": False,
            "maghrib": True, "isha": False,
        }

    def mark(on: bool) -> str:
        return "✅" if on else "❌"

    master = "🔔 اعلان‌ها: روشن" if settings.get("enabled") else "🔕 اعلان‌ها: خاموش"
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton(master)],
            [
                KeyboardButton(f"{mark(settings.get('fajr'))} اذان صبح"),
                KeyboardButton(f"{mark(settings.get('dhuhr'))} اذان ظهر"),
            ],
            [
                KeyboardButton(f"{mark(settings.get('asr'))} اذان عصر"),
                KeyboardButton(f"{mark(settings.get('maghrib'))} اذان مغرب"),
            ],
            [
                KeyboardButton(f"{mark(settings.get('isha'))} اذان عشاء"),
            ],
            [KeyboardButton("🔄 همه روشن"), KeyboardButton("⏹ همه خاموش")],
            [KeyboardButton("🔙 بازگشت به مذهبی")],
        ],
        resize_keyboard=True,
    )


def get_fun_keyboard():
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("📖 فال حافظ"), KeyboardButton("😂 جوک روز")],
            [KeyboardButton("🧠 دانستنی روز"), KeyboardButton("💪 چالش امروز")],
            [KeyboardButton("💖 جمله انگیزشی")],
            [KeyboardButton("🔙 بازگشت به بیشتر")],
        ],
        resize_keyboard=True,
    )


def get_joke_keyboard():
    """کیبورد دسته‌بندی جوک"""
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("🎲 جوک تصادفی"), KeyboardButton("😄 عمومی")],
            [KeyboardButton("🤣 ترکی"), KeyboardButton("😂 رشتی")],
            [KeyboardButton("😏 قزوینی"), KeyboardButton("👨 مردان")],
            [KeyboardButton("👩 زنان"), KeyboardButton("🤑 اصفهانی")],
            [KeyboardButton("🔞 سکسی"), KeyboardButton("🎭 متفرقه")],
            [KeyboardButton("💀 زشت")],
            [KeyboardButton("🔙 بازگشت به سرگرمی")],
        ],
        resize_keyboard=True,
    )



def get_profile_keyboard():
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("👤 پروفایل من"), KeyboardButton("📊 آمار من")],
            [KeyboardButton("🎂 ذخیره تاریخ تولد")],
            [KeyboardButton("🔙 بازگشت به بیشتر")],
        ],
        resize_keyboard=True,
    )


def get_country_keyboard():
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("🇮🇷 ایران"), KeyboardButton("🇮🇶 عراق")],
            [KeyboardButton("🔙 بازگشت")],
        ],
        resize_keyboard=True,
    )

def get_iran_cities_keyboard():
    buttons = []
    row = []
    for city in IRAN_CITIES:
        row.append(KeyboardButton(city))
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([KeyboardButton("🔙 بازگشت")])
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)

def get_iraq_cities_keyboard():
    buttons = []
    row = []
    for city in IRAQ_CITIES:
        row.append(KeyboardButton(city))
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([KeyboardButton("🔙 بازگشت")])
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)

def get_language_keyboard():
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("فارسی 🇮🇷"), KeyboardButton("English 🇬🇧"), KeyboardButton("العربية 🇸🇦")],
            [KeyboardButton("🔙 بازگشت")],
        ],
        resize_keyboard=True,
    )

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
                    weather_text = (
                        f"🌡️ دما: {weather['temp']}°C" + chr(10) +
                        f"🌤️ وضعیت: {weather['condition']}" + chr(10) +
                        f"💧 رطوبت: {weather['humidity']}%"
                    )
        except Exception as e:
            from bot.logger import logger
            logger.error(f"calendar weather: {e}")
            weather = get_weather(city)
            if weather:
                weather_text = (
                    f"🌡️ دما: {weather['temp']}°C" + chr(10) +
                    f"🌤️ وضعیت: {weather['condition']}" + chr(10) +
                    f"💧 رطوبت: {weather['humidity']}%"
                )

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



def get_font_keyboard():
    """کیبورد فونت: فارسی / انگلیسی / همه"""
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("🇬🇧 فونت انگلیسی"), KeyboardButton("🇮🇷 فونت فارسی")],
            [KeyboardButton("🌈 همه فونت‌ها"), KeyboardButton("📋 لیست فونت‌ها")],
            [KeyboardButton("🔙 بازگشت به بیشتر")],
        ],
        resize_keyboard=True,
    )


def get_font_en_keyboard():
    from bot.features.fonts.converter import EN_STYLES
    from bot.features.fonts.styles import FONT_NAMES
    buttons, row = [], []
    for k in EN_STYLES:
        label = FONT_NAMES.get(k, k)[:18]
        row.append(KeyboardButton(label))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([KeyboardButton("🔙 بازگشت فونت")])
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)


def get_font_fa_keyboard():
    from bot.features.fonts.converter import FA_STYLES
    from bot.features.fonts.styles import FONT_NAMES
    buttons, row = [], []
    for k in FA_STYLES:
        label = FONT_NAMES.get(k, k)[:18]
        row.append(KeyboardButton(label))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([KeyboardButton("🔙 بازگشت فونت")])
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)


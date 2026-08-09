from telegram import (
    InlineKeyboardButton, InlineKeyboardMarkup,
    KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove,
)
import jdatetime
import pytz
from datetime import datetime
from bot.config import config
from bot.api.calendar import get_today_tehran, get_hijri_date, get_shamsi_events, get_hijri_events
from bot.api.prayer import get_prayer_times, get_next_prayer_time
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
    """پیام اصلی کوتاه، تمیز و خوانا"""
    now = datetime.now(pytz.timezone(config.TIMEZONE))
    today = get_today_tehran()
    country = get_user_country(user_id)

    # ── تاریخ‌ها (فشرده) ──
    weekday = PERSIAN_WEEKDAYS[today.weekday()]
    month_name = PERSIAN_MONTHS[today.month]
    shamsi = f"{weekday} {to_persian_num(today.day)} {month_name} {to_persian_num(today.year)}"

    greg = today.togregorian()
    miladi = greg.strftime("%d %b %Y")

    hijri = get_hijri_date(greg)
    hijri_str = f"{to_persian_num(hijri['day'])} {hijri['month_name']} {to_persian_num(hijri['year'])}"

    # ── مناسبت‌ها (فقط امروز، بدون فردا) ──
    events = []
    for e in get_shamsi_events(today.year, today.month, today.day):
        if e and "هیچ مناسبت" not in e:
            events.append(e)
    for e in get_hijri_events(hijri["month"], hijri["day"]):
        if e and "هیچ مناسبت" not in e:
            events.append(e)
    # حذف تکراری و محدود کردن به ۳ مورد
    seen = set()
    unique_events = []
    for e in events:
        if e not in seen:
            seen.add(e)
            unique_events.append(e)
        if len(unique_events) >= 3:
            break
    events_text = "\n".join(f"• {e}" for e in unique_events) if unique_events else "• مناسبت خاصی ثبت نشده"

    # ── اوقات شرعی ──
    prayer_times = get_prayer_times(city, country=country)
    if prayer_times:
        # فقط اذان‌های اصلی (بدون طلوع)
        order = ["اذان صبح", "اذان ظهر", "اذان عصر", "اذان مغرب", "اذان عشاء"]
        prayer_lines = [f"• {k}: {prayer_times[k]}" for k in order if k in prayer_times]
        prayer_text = "\n".join(prayer_lines)

        next_prayer_text = ""
        result = get_next_prayer_time(prayer_times, now)
        if result and result[0]:
            name, delta = result
            hours = delta.seconds // 3600
            minutes = (delta.seconds % 3600) // 60
            next_prayer_text = (
                f"\n⏳ تا {name}: "
                f"**{to_persian_num(hours)}س {to_persian_num(minutes)}د**"
            )
    else:
        prayer_text = "• در دسترس نیست"
        next_prayer_text = ""

    # ── آب‌وهوا (یک خط) ──
    weather = get_weather(city)
    if weather:
        weather_text = f"{weather['temp']}°C  •  {weather['condition']}  •  رطوبت {weather['humidity']}٪"
    else:
        weather_text = "در دسترس نیست"

    # ── قیمت بازار (یک خط) ──
    market = await get_market_prices()
    dollar = market.get("dollar")
    gold18 = market.get("gold18")
    parts = []
    if dollar:
        parts.append(f"💵 {to_persian_num(f'{dollar:,}')}")
    if gold18:
        parts.append(f"🥇 {to_persian_num(f'{gold18:,}')}")
    market_text = "  |  ".join(parts) if parts else "در دسترس نیست"

    # ── انگیزشی ──
    motivation = get_motivation()

    # ── ساخت پیام نهایی ──
    message = (
        f"{get_text(user_id, 'welcome', name=user_name)}\n\n"
        f"📅 {shamsi}\n"
        f"🌙 {hijri_str}  •  📆 {miladi}\n\n"
        f"📌 **مناسبت امروز**\n{events_text}\n\n"
        f"🕌 **اوقات شرعی ({city})**\n{prayer_text}{next_prayer_text}\n\n"
        f"🌦️ {weather_text}\n"
        f"📊 {market_text}\n\n"
        f"💖 {motivation}"
    )
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
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
        input_field_placeholder="پیام بنویسید یا از دکمه‌ها استفاده کنید...",
    )


def get_more_keyboard():
    """منوی بیشتر: مبدل تاریخ + محاسبه سن"""
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("🔄 مبدل تاریخ")],
            [KeyboardButton("🎂 محاسبه سن دقیق")],
            [KeyboardButton("🔙 بازگشت")],
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
    try:
        target = jdatetime.date(year, month, day)
        date_str = f"{PERSIAN_WEEKDAYS[target.weekday()]} {to_persian_num(target.day)} {PERSIAN_MONTHS[target.month]} {to_persian_num(target.year)}/{to_persian_num(f'{target.month:02d}')}/{to_persian_num(f'{target.day:02d}')}"
        shamsi = get_shamsi_events(year, month, day)
        shamsi_text = "\n".join([f"• {e}" for e in shamsi])
        hijri = get_hijri_date(target.togregorian())
        hijri_events_list = get_hijri_events(hijri['month'], hijri['day'])
        hijri_text = "\n".join([f"• {e}" for e in hijri_events_list])
        city = get_user_city(user_id)
        country = get_user_country(user_id)
        prayer = get_prayer_times(city, country=country)
        prayer_text = ""
        if prayer:
            prayer_text = "\n".join([f"🕌 {k}: {v}" for k, v in prayer.items()])
        else:
            prayer_text = "⚠️ " + get_text(user_id, "no_events")
        weather = get_weather(city)
        weather_text = ""
        if weather:
            weather_text = f"🌡️ دما: {weather['temp']}°C\n🌤️ وضعیت: {weather['condition']}\n💧 رطوبت: {weather['humidity']}%"
        else:
            weather_text = "⚠️ " + get_text(user_id, "no_events")
        return (
            f"📅 **{date_str}**\n"
            f"🌙 **قمری:** {to_persian_num(hijri['day'])} {hijri['month_name']} {to_persian_num(hijri['year'])}\n\n"
            f"📌 **مناسبت‌های شمسی:**\n{shamsi_text}\n\n"
            f"📌 **مناسبت‌های قمری:**\n{hijri_text}\n\n"
            f"⏰ **اوقات شرعی ({city}):**\n{prayer_text}\n\n"
            f"🌦️ **آب و هوا:**\n{weather_text}\n\n"
            "🔄 با دکمه‌های زیر روز یا ماه را تغییر دهید."
        )
    except Exception:
        return "❌ خطا در نمایش تقویم."

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
import jdatetime
import pytz
from datetime import datetime
from bot.config import config
from bot.api.calendar import get_today_tehran, get_hijri_date, get_shamsi_events, get_hijri_events
from bot.api.prayer import get_prayer_times, get_next_prayer_time
from bot.api.weather import get_weather
from bot.utils.texts import get_text
from bot.utils.motivation import get_motivation
from bot.database import get_user_city, get_user_language

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

def build_message(user_id, user_name, city):
    lang = get_user_language(user_id)
    now = datetime.now(pytz.timezone(config.TIMEZONE))
    today = get_today_tehran()

    # تاریخ شمسی
    weekday = PERSIAN_WEEKDAYS[today.weekday()]
    month_name = PERSIAN_MONTHS[today.month]
    year_p = to_persian_num(today.year)
    month_p = to_persian_num(f"{today.month:02d}")
    day_p = to_persian_num(f"{today.day:02d}")
    persian_date = f"{weekday} {to_persian_num(today.day)} {month_name} {year_p}/{month_p}/{day_p}"

    # تاریخ میلادی
    greg = today.togregorian()
    miladi_date = greg.strftime("%B %d, %A") + f" {greg.year}/{greg.month:02d}/{greg.day:02d}"

    # تاریخ قمری (با اعداد فارسی)
    hijri = get_hijri_date(greg)
    hijri_date = f"{to_persian_num(hijri['day'])} {hijri['month_name']} {to_persian_num(hijri['year'])} / {to_persian_num(hijri['month'])} / {to_persian_num(hijri['day'])}"

    # مناسبت‌ها
    hijri_events_list = get_hijri_events(hijri['month'], hijri['day'])
    hijri_events_text = "\n".join([f"• {e}" for e in hijri_events_list])

    tomorrow = today + jdatetime.timedelta(days=1)
    hijri_tomorrow = get_hijri_date(tomorrow.togregorian())
    hijri_tomorrow_events = get_hijri_events(hijri_tomorrow['month'], hijri_tomorrow['day'])
    hijri_tomorrow_text = "\n".join([f"• {e}" for e in hijri_tomorrow_events])

    shamsi_events_list = get_shamsi_events(today.year, today.month, today.day)
    shamsi_text = "\n".join([f"• {e}" for e in shamsi_events_list])

    shamsi_tomorrow = get_shamsi_events(tomorrow.year, tomorrow.month, tomorrow.day)
    shamsi_tomorrow_text = "\n".join([f"• {e}" for e in shamsi_tomorrow])

    # اوقات شرعی (کلیدهای فارسی)
    prayer_times = get_prayer_times(city)
    prayer_text = ""
    if prayer_times:
        for key, time in prayer_times.items():
            prayer_text += f"🕌 {key}: {time}\n"
    else:
        prayer_text = "⚠️ " + get_text(user_id, "no_events")

    # زمان تا اذان بعدی
    next_prayer_text = ""
    if prayer_times:
        result = get_next_prayer_time(prayer_times, now)
        if result and result[0]:
            name, delta = result
            hours = delta.seconds // 3600
            minutes = (delta.seconds % 3600) // 60
            next_prayer_text = get_text(
                user_id, "next_prayer",
                name=name,
                hours=to_persian_num(hours),
                minutes=to_persian_num(minutes)
            ) + "\n"

    # آب و هوا
    weather = get_weather(city)
    weather_text = ""
    if weather:
        weather_text = f"🌡️ دما: {weather['temp']}°C\n🌤️ وضعیت: {weather['condition']}\n💧 رطوبت: {weather['humidity']}%"
    else:
        weather_text = "⚠️ " + get_text(user_id, "no_events")

    motivation = get_motivation()

    message = (
        get_text(user_id, "welcome", name=user_name) + "\n\n" +
        f"📅 **امروز (شمسی):** {persian_date}\n" +
        f"📅 **امروز (میلادی):** {miladi_date}\n" +
        f"🌙 **امروز (قمری):** {hijri_date}\n\n" +
        f"📌 **مناسبت‌های قمری امروز:**\n{hijri_events_text}\n\n" +
        f"📌 **مناسبت‌های قمری فردا:**\n{hijri_tomorrow_text}\n\n" +
        f"📌 **مناسبت‌های شمسی امروز:**\n{shamsi_text}\n\n" +
        f"🔮 **مناسبت‌های شمسی فردا:**\n{shamsi_tomorrow_text}\n\n" +
        get_text(user_id, "prayer", city=city) + "\n" + prayer_text +
        next_prayer_text + "\n" +
        get_text(user_id, "weather", city=city) + "\n" + weather_text + "\n\n" +
        get_text(user_id, "motivation") + "\n" + motivation + "\n\n" +
        get_text(user_id, "change_city")
    )
    return message

from bot.api.tgju import get_dollar_price, get_gold18_price

# ... داخل build_message ...

# قیمت دلار و طلا
dollar = get_dollar_price()
gold18 = get_gold18_price()

market_text = ""
if dollar:
    market_text += f"💵 دلار: {to_persian_num(f'{dollar:,}')} ریال\n"
if gold18:
    market_text += f"🥇 طلای ۱۸ عیار: {to_persian_num(f'{gold18:,}')} ریال\n"

if not market_text:
    market_text = "⚠️ قیمت بازار در دسترس نیست.\n"
    
def get_city_buttons(user_id):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("تهران", callback_data="city_تهران"),
         InlineKeyboardButton("مشهد", callback_data="city_مشهد"),
         InlineKeyboardButton("قم", callback_data="city_قم")],
        [InlineKeyboardButton("اصفهان", callback_data="city_اصفهان"),
         InlineKeyboardButton("شیراز", callback_data="city_شیراز"),
         InlineKeyboardButton("تبریز", callback_data="city_تبریز")],
        [InlineKeyboardButton("🌍 زبان", callback_data="language_menu"),
         InlineKeyboardButton("📅 تقویم", callback_data="calendar_menu"),
         InlineKeyboardButton("🔄 بروزرسانی", callback_data="refresh_main")]
    ])

def get_language_buttons():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("فارسی 🇮🇷", callback_data="lang_fa"),
         InlineKeyboardButton("English 🇬🇧", callback_data="lang_en")],
        [InlineKeyboardButton("العربية 🇸🇦", callback_data="lang_ar"),
         InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_main")]
    ])

def get_calendar_buttons(year, month, day, user_id):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("◀️ روز قبل", callback_data=f"day_{year}_{month}_{day-1}"),
         InlineKeyboardButton("📅 امروز", callback_data="calendar_today"),
         InlineKeyboardButton("روز بعد ▶️", callback_data=f"day_{year}_{month}_{day+1}")],
        [InlineKeyboardButton("◀️ ماه قبل", callback_data=f"cal_{year}_{month-1}_{day}"),
         InlineKeyboardButton("ماه بعد ▶️", callback_data=f"cal_{year}_{month+1}_{day}")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_main")]
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
        prayer = get_prayer_times(city)
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
    except Exception as e:
        return "❌ خطا در نمایش تقویم."

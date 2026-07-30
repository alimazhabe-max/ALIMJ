import requests
from datetime import datetime, timedelta
import pytz
from bot.config import config
from bot.logger import logger

tehran_tz = pytz.timezone(config.TIMEZONE)
_cache_data = {}
_cache_time = {}

def get_prayer_times(city, country="Iran", method=config.PRAYER_METHOD):
    """دریافت اوقات شرعی با کش ۵ دقیقه‌ای"""
    key = f"{city}_{country}"
    now = datetime.now().timestamp()

    # بررسی کش
    if key in _cache_data and now - _cache_time.get(key, 0) < config.CACHE_TTL:
        return _cache_data[key]

    try:
        url = f"https://api.aladhan.com/v1/timingsByCity?city={city}&country={country}&method={method}&school=0"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        timings = data["data"]["timings"]

        result = {
            "Fajr": timings["Fajr"],
            "Sunrise": timings["Sunrise"],
            "Dhuhr": timings["Dhuhr"],
            "Asr": timings["Asr"],
            "Maghrib": timings["Maghrib"],
            "Isha": timings["Isha"],
        }

        _cache_data[key] = result
        _cache_time[key] = now
        return result
    except Exception as e:
        logger.error(f"Error fetching prayer times for {city}: {e}")
        return None

def get_next_prayer_time(prayer_times, now_dt):
    """محاسبه زمان باقی‌مانده تا اذان بعدی"""
    if not prayer_times:
        return None, None

    prayer_keys = ["Fajr", "Dhuhr", "Asr", "Maghrib", "Isha"]
    today = now_dt.date()
    prayer_datetimes = []

    for key in prayer_keys:
        if key in prayer_times:
            try:
                hour, minute = map(int, prayer_times[key].split(':'))
                dt = datetime.combine(today, datetime.min.time().replace(hour=hour, minute=minute))
                dt = tehran_tz.localize(dt)
                prayer_datetimes.append((key, dt))
            except:
                continue

    if not prayer_datetimes:
        return None, None

    future_prayers = [(key, dt) for key, dt in prayer_datetimes if dt > now_dt]
    if future_prayers:
        next_prayer = min(future_prayers, key=lambda x: x[1])
        return next_prayer[0], next_prayer[1] - now_dt
    else:
        next_day_prayers = [(key, dt + timedelta(days=1)) for key, dt in prayer_datetimes]
        next_prayer = min(next_day_prayers, key=lambda x: x[1])
        return next_prayer[0], next_prayer[1] - now_dt

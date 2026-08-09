"""پیش‌بینی هوا، AQI، فاصله شهرها"""
import math
import requests
from datetime import datetime
from bot.config import config
from bot.logger import logger

_cache = {}
_cache_t = {}

CITY_COORDS = {
    "تهران": (35.6892, 51.3890), "مشهد": (36.2970, 59.6062), "اصفهان": (32.6546, 51.6680),
    "شیراز": (29.5918, 52.5837), "تبریز": (38.0962, 46.2738), "قم": (34.6416, 50.8746),
    "کرج": (35.8400, 50.9391), "اهواز": (31.3183, 48.6706), "کرمانشاه": (34.3142, 47.0650),
    "ارومیه": (37.5527, 45.0761), "رشت": (37.2808, 49.5832), "کرمان": (30.2832, 57.0788),
    "یزد": (31.8974, 54.3569), "همدان": (34.7983, 48.5146), "نجف": (31.9956, 44.3147),
    "کربلا": (32.6163, 44.0249), "بغداد": (33.3152, 44.3661),
}


def pn(n):
    return str(n).translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))


def weather_forecast(city: str) -> str:
    key = f"fc_{city}"
    now = datetime.now().timestamp()
    if key in _cache and now - _cache_t.get(key, 0) < config.CACHE_TTL:
        return _cache[key]
    try:
        url = f"https://wttr.in/{city}?format=j1&lang=en"
        r = requests.get(url, timeout=12)
        r.raise_for_status()
        data = r.json()
        lines = [f"🌤 **پیش‌بینی هوای {city}**\n"]
        for i, day in enumerate(data.get("weather", [])[:3]):
            date = day.get("date", "")
            avg = day.get("avgtempC", "?")
            mx = day.get("maxtempC", "?")
            mn = day.get("mintempC", "?")
            desc = day.get("hourly", [{}])[4].get("weatherDesc", [{}])[0].get("value", "")
            label = ["امروز", "فردا", "پس‌فردا"][i] if i < 3 else date
            lines.append(f"• {label}: {mn}°–{mx}° (میانگین {avg}°) — {desc}")
        result = "\n".join(lines)
        _cache[key] = result
        _cache_t[key] = now
        return result
    except Exception as e:
        logger.error(f"forecast {city}: {e}")
        return f"❌ پیش‌بینی هوای {city} در دسترس نیست."


def air_quality(city: str) -> str:
    key = f"aqi_{city}"
    now = datetime.now().timestamp()
    if key in _cache and now - _cache_t.get(key, 0) < config.CACHE_TTL:
        return _cache[key]
    try:
        # wttr.in گاهی air quality دارد
        url = f"https://wttr.in/{city}?format=j1"
        r = requests.get(url, timeout=10)
        data = r.json()
        current = data.get("current_condition", [{}])[0]
        # تقریبی از دید و رطوبت
        humidity = current.get("humidity", "?")
        vis = current.get("visibility", "?")
        result = (
            f"🌫 **کیفیت هوا — {city}**\n\n"
            f"💧 رطوبت: {humidity}%\n"
            f"👁 دید: {vis} km\n\n"
            f"(AQI دقیق نیاز به سرویس تخصصی دارد؛ این مقادیر تقریبی‌اند)"
        )
        _cache[key] = result
        _cache_t[key] = now
        return result
    except Exception as e:
        logger.error(f"aqi {city}: {e}")
        return f"❌ کیفیت هوای {city} در دسترس نیست."


def city_distance(city1: str, city2: str) -> str:
    c1 = CITY_COORDS.get(city1)
    c2 = CITY_COORDS.get(city2)
    if not c1 or not c2:
        return f"❌ یکی از شهرها در لیست نیست.\nشهرهای موجود: {', '.join(list(CITY_COORDS.keys())[:12])}..."
    # Haversine
    R = 6371
    lat1, lon1 = math.radians(c1[0]), math.radians(c1[1])
    lat2, lon2 = math.radians(c2[0]), math.radians(c2[1])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    dist = 2 * R * math.asin(math.sqrt(a))
    return (
        f"🗺 **فاصله بین شهرها**\n\n"
        f"{city1} ↔ {city2}\n"
        f"📏 حدود **{pn(f'{dist:.0f}')} کیلومتر**"
    )

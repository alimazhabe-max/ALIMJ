"""آب و هوای لحظه‌ای — Open-Meteo (پایدار) + wttr پشتیبان — وضعیت فارسی"""
import requests
from datetime import datetime
from bot.logger import logger
from bot.config import config

_cache_data = {}
_cache_time = {}

# مختصات شهرهای پرتکرار (هم‌راستا با weather_extra)
CITY_COORDS = {
    "تهران": (35.6892, 51.3890), "مشهد": (36.2970, 59.6062), "اصفهان": (32.6546, 51.6680),
    "شیراز": (29.5918, 52.5837), "تبریز": (38.0962, 46.2738), "قم": (34.6416, 50.8746),
    "کرج": (35.8400, 50.9391), "اهواز": (31.3183, 48.6706), "کرمانشاه": (34.3142, 47.0650),
    "ارومیه": (37.5527, 45.0761), "رشت": (37.2808, 49.5832), "کرمان": (30.2832, 57.0788),
    "یزد": (31.8974, 54.3569), "همدان": (34.7983, 48.5146), "اردبیل": (38.2498, 48.2933),
    "زاهدان": (29.4963, 60.8629), "بندرعباس": (27.1832, 56.2666), "ساری": (36.5633, 53.0601),
    "قزوین": (36.2688, 50.0041), "خرم‌آباد": (33.4878, 48.3558), "سنندج": (35.3219, 46.9862),
    "بوشهر": (28.9234, 50.8203), "اراک": (34.0917, 49.6892), "زنجان": (36.6736, 48.4787),
    "گرگان": (36.8427, 54.4439), "سمنان": (35.5769, 53.3953), "بجنورد": (37.4750, 57.3333),
    "ایلام": (33.6374, 46.4226), "یاسوج": (30.6682, 51.5880), "بیرجند": (32.8663, 59.2211),
    "ساوه": (35.0213, 50.3566), "کیش": (26.5570, 53.9800), "قشم": (26.9581, 56.2719),
    "چابهار": (25.2919, 60.6430), "نجف": (31.9956, 44.3147), "کربلا": (32.6163, 44.0249),
    "بغداد": (33.3152, 44.3661),
}

WEATHER_CODES = {
    0: "آفتابی ☀️", 1: "عمدتاً صاف 🌤", 2: "نیمه‌ابری ⛅", 3: "ابری ☁️",
    45: "مه 🌫", 48: "مه یخی 🌫", 51: "باران ریز 🌦", 53: "باران متوسط 🌧",
    55: "باران شدید 🌧", 61: "باران 🌧", 63: "باران متوسط 🌧", 65: "باران شدید ⛈",
    71: "برف ❄️", 73: "برف متوسط ❄️", 75: "برف سنگین ❄️", 80: "رگبار 🌦",
    81: "رگبار متوسط 🌧", 82: "رگبار شدید ⛈", 95: "رعدوبرق ⛈", 96: "تگرگ 🌨",
}

EN2FA = {
    "Sunny": "آفتابی ☀️", "Clear": "صاف ☀️", "Partly cloudy": "نیمه‌ابری ⛅",
    "Cloudy": "ابری ☁️", "Overcast": "ابری کامل ☁️", "Mist": "مه 🌫",
    "Fog": "مه 🌫", "Patchy rain possible": "احتمال باران 🌦",
    "Light rain": "باران خفیف 🌦", "Moderate rain": "باران متوسط 🌧",
    "Heavy rain": "باران شدید 🌧", "Rain": "بارانی 🌧",
    "Thundery outbreaks possible": "رعدوبرق ⛈", "Thunderstorm": "رعدوبرق ⛈",
    "Snow": "برفی ❄️", "Light snow": "برف خفیف ❄️", "Heavy snow": "برف سنگین ❄️",
    "Blizzard": "کولاک ❄️", "Haze": "غبار 🌫",
}


def _norm_city(city: str) -> str:
    return (city or "").strip().replace("ي", "ی").replace("ك", "ک") or "تهران"


def _coords(city: str):
    c = _norm_city(city)
    if c in CITY_COORDS:
        return CITY_COORDS[c]
    for k, v in CITY_COORDS.items():
        if c in k or k in c:
            return v
    # geocode
    try:
        r = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": f"{c}, Iran", "format": "json", "limit": 1},
            headers={"User-Agent": "ALIMJBot/2.0"},
            timeout=8,
        )
        if r.status_code == 200 and r.json():
            item = r.json()[0]
            return float(item["lat"]), float(item["lon"])
    except Exception as e:
        logger.warning(f"weather geocode: {e}")
    return CITY_COORDS["تهران"]


def get_weather(city):
    """
    خروجی dict:
      temp, feels_like, condition, humidity, wind, pressure, visibility, high, low
    """
    city = _norm_city(city)
    key = city
    now = datetime.now().timestamp()
    ttl = getattr(config, "CACHE_TTL", 300)

    if key in _cache_data and now - _cache_time.get(key, 0) < ttl:
        return _cache_data[key]

    result = _from_open_meteo(city)
    if not result:
        result = _from_wttr(city)

    if result:
        _cache_data[key] = result
        _cache_time[key] = now
    return result


def _from_open_meteo(city: str):
    try:
        lat, lon = _coords(city)
        r = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": lat,
                "longitude": lon,
                "current": "temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,wind_speed_10m,surface_pressure",
                "daily": "temperature_2m_max,temperature_2m_min",
                "timezone": "Asia/Tehran",
                "forecast_days": 1,
            },
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=12,
        )
        if r.status_code != 200:
            return None
        data = r.json()
        cur = data.get("current") or {}
        daily = data.get("daily") or {}
        code = int(cur.get("weather_code") or 0)
        result = {
            "temp": _num(cur.get("temperature_2m")),
            "feels_like": _num(cur.get("apparent_temperature")),
            "condition": WEATHER_CODES.get(code, "نامشخص"),
            "humidity": _num(cur.get("relative_humidity_2m")),
            "wind": _num(cur.get("wind_speed_10m")),
            "pressure": _num(cur.get("surface_pressure")),
            "high": _num((daily.get("temperature_2m_max") or [None])[0]),
            "low": _num((daily.get("temperature_2m_min") or [None])[0]),
            "source": "open-meteo",
        }
        return result
    except Exception as e:
        logger.error(f"open-meteo weather {city}: {e}")
        return None


def _from_wttr(city: str):
    try:
        r = requests.get(
            f"https://wttr.in/{city}?format=j1",
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=10,
        )
        r.raise_for_status()
        data = r.json()
        current = data["current_condition"][0]
        desc = current["weatherDesc"][0]["value"]
        # فارسی اگر lang_fa بود
        try:
            if current.get("lang_fa"):
                desc = current["lang_fa"][0].get("value") or desc
        except Exception:
            pass
        desc = EN2FA.get(desc, EN2FA.get(desc.title(), desc))
        # اگر هنوز انگلیسی ساده بود
        for en, fa in EN2FA.items():
            if en.lower() in str(desc).lower():
                desc = fa
                break

        weather_today = (data.get("weather") or [{}])[0]
        result = {
            "temp": current.get("temp_C"),
            "feels_like": current.get("FeelsLikeC"),
            "condition": desc,
            "humidity": current.get("humidity"),
            "wind": current.get("windspeedKmph"),
            "pressure": current.get("pressure"),
            "visibility": current.get("visibility"),
            "high": weather_today.get("maxtempC"),
            "low": weather_today.get("mintempC"),
            "source": "wttr",
        }
        return result
    except Exception as e:
        logger.error(f"wttr weather {city}: {e}")
        return None


def _num(v):
    if v is None or v == "":
        return None
    try:
        f = float(v)
        return int(f) if f == int(f) else round(f, 1)
    except Exception:
        return v


def format_weather(city: str, weather: dict | None) -> str:
    """متن زیبای فارسی برای نمایش"""
    if not weather:
        return f"⚠️ آب و هوای {city} موقتاً در دسترس نیست."
    lines = [f"🌦️ آب و هوای {city}"]
    temp = weather.get("temp")
    feels = weather.get("feels_like")
    if temp is not None:
        line = f"🌡️ دما: {temp}°C"
        if feels is not None and feels != temp:
            line += f"  (احساس: {feels}°C)"
        lines.append(line)
    if weather.get("condition"):
        lines.append(f"🌤️ وضعیت: {weather['condition']}")
    hi, lo = weather.get("high"), weather.get("low")
    if hi is not None or lo is not None:
        lines.append(f"🔼 کمینه/بیشینه: {lo if lo is not None else '—'}° / {hi if hi is not None else '—'}°")
    if weather.get("humidity") is not None:
        lines.append(f"💧 رطوبت: {weather['humidity']}%")
    if weather.get("wind") is not None:
        lines.append(f"💨 باد: {weather['wind']} km/h")
    if weather.get("pressure") is not None:
        lines.append(f"📉 فشار: {weather['pressure']} hPa")
    if weather.get("visibility") is not None:
        lines.append(f"👁 دید: {weather['visibility']} km")
    return "\n".join(lines)

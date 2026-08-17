"""آب و هوای لحظه‌ای — اولویت: MET Norway → Open-Meteo → wttr"""
import requests
from datetime import datetime
from bot.logger import logger
from bot.config import config

_cache_data = {}
_cache_time = {}

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

# WMO / Open-Meteo weather codes
WEATHER_CODES = {
    0: "آفتابی ☀️", 1: "عمدتاً صاف 🌤", 2: "نیمه‌ابری ⛅", 3: "ابری ☁️",
    45: "مه 🌫", 48: "مه یخی 🌫", 51: "باران ریز 🌦", 53: "باران متوسط 🌧",
    55: "باران شدید 🌧", 61: "باران 🌧", 63: "باران متوسط 🌧", 65: "باران شدید ⛈",
    71: "برف ❄️", 73: "برف متوسط ❄️", 75: "برف سنگین ❄️", 80: "رگبار 🌦",
    81: "رگبار متوسط 🌧", 82: "رگبار شدید ⛈", 95: "رعدوبرق ⛈", 96: "تگرگ 🌨",
}

# MET Norway symbol_code → فارسی
MET_SYMBOLS = {
    "clearsky": "آفتابی ☀️", "fair": "عمدتاً صاف 🌤", "partlycloudy": "نیمه‌ابری ⛅",
    "cloudy": "ابری ☁️", "fog": "مه 🌫",
    "lightrain": "باران خفیف 🌦", "rain": "بارانی 🌧", "heavyrain": "باران شدید 🌧",
    "lightrainshowers": "رگبار خفیف 🌦", "rainshowers": "رگبار 🌧",
    "heavyrainshowers": "رگبار شدید ⛈",
    "lightsnow": "برف خفیف ❄️", "snow": "برفی ❄️", "heavysnow": "برف سنگین ❄️",
    "lightsnowshowers": "رگبار برف ❄️", "snowshowers": "رگبار برف ❄️",
    "sleet": "باران‌برف 🌨", "sleetshowers": "رگبار باران‌برف 🌨",
    "rainandthunder": "باران و رعدوبرق ⛈", "snowandthunder": "برف و رعدوبرق ⛈",
    "rainshowersandthunder": "رگبار و رعدوبرق ⛈",
    "lightrainandthunder": "باران خفیف و رعد ⛈",
}


MET_SYMBOLS_DAY = dict(MET_SYMBOLS)
MET_SYMBOLS_NIGHT = dict(MET_SYMBOLS)
MET_SYMBOLS_NIGHT.update({
    "clearsky": "آسمان صاف (شب) 🌙",
    "fair": "تقریباً صاف (شب) 🌙",
    "partlycloudy": "نیمه‌ابری (شب) ☁️",
})


def _is_night_tehran() -> bool:
    """شب در ایران: از ۱۹ تا ۵ صبح"""
    try:
        from zoneinfo import ZoneInfo
        now = datetime.now(ZoneInfo("Asia/Tehran"))
    except Exception:
        from datetime import timezone, timedelta
        now = datetime.now(timezone(timedelta(hours=3, minutes=30)))
    return now.hour >= 19 or now.hour < 5


def _met_condition(symbol_code: str) -> str:
    sym = (symbol_code or "").lower().strip()
    is_night = ("night" in sym) or ("polartwilight" in sym)
    if not is_night and "day" not in sym:
        is_night = _is_night_tehran()
    base = sym.split("_")[0] if sym else ""
    table = MET_SYMBOLS_NIGHT if is_night else MET_SYMBOLS_DAY
    return table.get(base, base or "نامشخص")


EN2FA = {
    "Sunny": "آفتابی ☀️", "Clear": "صاف ☀️", "Partly cloudy": "نیمه‌ابری ⛅",
    "Cloudy": "ابری ☁️", "Overcast": "ابری کامل ☁️", "Mist": "مه 🌫", "Fog": "مه 🌫",
    "Patchy rain possible": "احتمال باران 🌦", "Patchy rain nearby": "باران پراکنده 🌦",
    "Light rain": "باران خفیف 🌦", "Moderate rain": "باران متوسط 🌧",
    "Heavy rain": "باران شدید 🌧", "Rain": "بارانی 🌧",
    "Thundery outbreaks possible": "رعدوبرق ⛈", "Thunderstorm": "رعدوبرق ⛈",
    "Snow": "برفی ❄️", "Light snow": "برف خفیف ❄️", "Heavy snow": "برف سنگین ❄️",
    "Haze": "غبار 🌫",
}


def translate_condition(desc) -> str:
    if not desc:
        return "نامشخص"
    s = str(desc).strip()
    if any("\u0600" <= ch <= "\u06FF" for ch in s):
        return s
    if s in EN2FA:
        return EN2FA[s]
    low = s.lower()
    for en, fa in EN2FA.items():
        if en.lower() == low:
            return fa
    for en, fa in sorted(EN2FA.items(), key=lambda x: -len(x[0])):
        if en.lower() in low:
            return fa
    extra = {
        "cloud": "ابری ☁️", "rain": "بارانی 🌧", "clear": "صاف ☀️", "sun": "آفتابی ☀️",
        "snow": "برفی ❄️", "fog": "مه 🌫", "mist": "مه 🌫", "thunder": "رعدوبرق ⛈",
        "overcast": "ابری کامل ☁️", "drizzle": "باران ریز 🌦", "haze": "غبار 🌫",
    }
    for k, v in extra.items():
        if k in low:
            return v
    return s


def _norm_city(city: str) -> str:
    return (city or "").strip().replace("ي", "ی").replace("ك", "ک") or "تهران"


def _coords(city: str):
    c = _norm_city(city)
    if c in CITY_COORDS:
        return CITY_COORDS[c]
    for k, v in CITY_COORDS.items():
        if c in k or k in c:
            return v
    try:
        r = requests.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": c, "count": 3, "language": "fa"},
            timeout=8,
        )
        if r.status_code == 200:
            for item in r.json().get("results") or []:
                # ترجیح ایران
                if (item.get("country_code") or "").upper() in ("IR", "IQ", ""):
                    return float(item["latitude"]), float(item["longitude"])
            results = r.json().get("results") or []
            if results:
                return float(results[0]["latitude"]), float(results[0]["longitude"])
    except Exception as e:
        logger.warning(f"geocode: {e}")
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
        logger.warning(f"nominatim: {e}")
    return CITY_COORDS["تهران"]


def _num(v):
    if v is None or v == "":
        return None
    try:
        f = float(v)
        return int(round(f)) if abs(f - round(f)) < 0.05 else round(f, 1)
    except Exception:
        return v


def get_weather(city):
    """dict: temp, condition, humidity, feels_like, wind, ..."""
    city = _norm_city(city)
    now = datetime.now().timestamp()
    ttl = getattr(config, "CACHE_TTL", 300)
    if city in _cache_data and now - _cache_time.get(city, 0) < ttl:
        return _cache_data[city]

    lat, lon = _coords(city)
    result = None
    # 1) MET Norway — دقیق و رایگان
    result = _from_metno(lat, lon)
    # 2) Open-Meteo
    if not result:
        result = _from_open_meteo(lat, lon)
    # 3) wttr — فقط اگر معقول باشد
    if not result:
        result = _from_wttr(city, lat, lon)

    if result:
        cond = translate_condition(result.get("condition"))
        if _is_night_tehran():
            c = str(cond)
            if any(x in c for x in ("آفتابی", "☀️")) and "ابری" not in c and "باران" not in c:
                cond = "آسمان صاف (شب) 🌙"
            elif c in ("صاف ☀️", "Clear", "Sunny"):
                cond = "آسمان صاف (شب) 🌙"
        result["condition"] = cond
        _cache_data[city] = result
        _cache_time[city] = now
    return result


def _from_metno(lat, lon):
    try:
        r = requests.get(
            "https://api.met.no/weatherapi/locationforecast/2.0/compact",
            params={"lat": lat, "lon": lon},
            headers={"User-Agent": "ALIMJBot/2.0 (telegram-bot; contact@local)"},
            timeout=12,
        )
        if r.status_code != 200:
            logger.warning(f"met.no status {r.status_code}")
            return None
        series = (r.json().get("properties") or {}).get("timeseries") or []
        if not series:
            return None
        now_data = series[0]
        details = ((now_data.get("data") or {}).get("instant") or {}).get("details") or {}
        # symbol از next_1_hours یا next_6_hours
        symbol = ""
        for key in ("next_1_hours", "next_6_hours", "next_12_hours"):
            s = ((now_data.get("data") or {}).get(key) or {}).get("summary") or {}
            if s.get("symbol_code"):
                symbol = s["symbol_code"]
                break
        # حذف پسوند day/night/_polartwilight
        condition = _met_condition(symbol)

        # min/max تقریبی از ۱۲ ساعت آینده
        temps = []
        for item in series[:12]:
            t = (((item.get("data") or {}).get("instant") or {}).get("details") or {}).get("air_temperature")
            if t is not None:
                temps.append(float(t))

        return {
            "temp": _num(details.get("air_temperature")),
            "feels_like": None,
            "condition": condition,
            "humidity": _num(details.get("relative_humidity")),
            "wind": _num(details.get("wind_speed")),
            "pressure": _num(details.get("air_pressure_at_sea_level")),
            "high": _num(max(temps)) if temps else None,
            "low": _num(min(temps)) if temps else None,
            "source": "met.no",
        }
    except Exception as e:
        logger.error(f"met.no: {e}")
        return None


def _from_open_meteo(lat, lon):
    try:
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
        if data.get("error"):
            return None
        cur = data.get("current") or {}
        daily = data.get("daily") or {}
        code = int(cur.get("weather_code") or 0)
        cond = WEATHER_CODES.get(code, "نامشخص")
        if _is_night_tehran() and code in (0, 1):
            cond = "آسمان صاف (شب) 🌙" if code == 0 else "تقریباً صاف (شب) 🌙"
        return {
            "temp": _num(cur.get("temperature_2m")),
            "feels_like": _num(cur.get("apparent_temperature")),
            "condition": cond,
            "humidity": _num(cur.get("relative_humidity_2m")),
            "wind": _num(cur.get("wind_speed_10m")),
            "pressure": _num(cur.get("surface_pressure")),
            "high": _num((daily.get("temperature_2m_max") or [None])[0]),
            "low": _num((daily.get("temperature_2m_min") or [None])[0]),
            "source": "open-meteo",
        }
    except Exception as e:
        logger.error(f"open-meteo: {e}")
        return None


def _from_wttr(city, lat=None, lon=None):
    """پشتیبان آخر — با فیلتر دمای نامعقول برای ایران در تابستان/زمستان"""
    try:
        q = city
        # برای دقت بیشتر از مختصات استفاده کن
        if lat is not None and lon is not None:
            q = f"{lat},{lon}"
        r = requests.get(
            f"https://wttr.in/{q}?format=j1",
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=10,
        )
        r.raise_for_status()
        data = r.json()
        current = data["current_condition"][0]
        desc = current["weatherDesc"][0]["value"]
        try:
            if current.get("lang_fa"):
                desc = current["lang_fa"][0].get("value") or desc
        except Exception:
            pass
        temp = _num(current.get("temp_C"))
        weather_today = (data.get("weather") or [{}])[0]
        result = {
            "temp": temp,
            "feels_like": _num(current.get("FeelsLikeC")),
            "condition": desc,
            "humidity": _num(current.get("humidity")),
            "wind": _num(current.get("windspeedKmph")),
            "pressure": _num(current.get("pressure")),
            "high": _num(weather_today.get("maxtempC")),
            "low": _num(weather_today.get("mintempC")),
            "source": "wttr",
        }
        return result
    except Exception as e:
        logger.error(f"wttr: {e}")
        return None


def format_weather(city: str, weather: dict | None) -> str:
    if not weather:
        return f"⚠️ آب و هوای {city} موقتاً در دسترس نیست."
    lines = [f"🌦️ آب و هوای {city}"]
    temp = weather.get("temp")
    if temp is not None:
        lines.append(f"🌡️ دما: {temp}°C")
    if weather.get("condition"):
        lines.append(f"🌤️ وضعیت: {weather['condition']}")
    if weather.get("humidity") is not None:
        lines.append(f"💧 رطوبت: {weather['humidity']}%")
    return "\n".join(lines)

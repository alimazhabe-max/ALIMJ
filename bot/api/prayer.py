import requests
from datetime import datetime, timedelta
import pytz
from bot.config import config
from bot.logger import logger

tehran_tz = pytz.timezone(config.TIMEZONE)
_cache_data = {}
_cache_time = {}

# -------------------------------------------------
# مختصات دقیق تمام شهرهای پشتیبانی‌شده توسط ربات
# (ایران + شهرهای زیارتی عراق)
# این مختصات باعث می‌شود خروجی دقیقاً با اپ‌های رسمی مچ شود
# -------------------------------------------------
CITY_COORDS = {
    # ────────── ایران (مطابق IRAN_CITIES در helpers.py) ──────────
    "تهران": (35.6892, 51.3890),
    "مشهد": (36.2605, 59.6168),
    "اصفهان": (32.6546, 51.6680),
    "شیراز": (29.5918, 52.5837),
    "تبریز": (38.0962, 46.2738),
    "قم": (34.6416, 50.8746),
    "کرج": (35.8400, 50.9391),
    "اهواز": (31.3183, 48.6706),
    "کرمانشاه": (34.3142, 47.0650),
    "ارومیه": (37.5527, 45.0761),
    "رشت": (37.2808, 49.5832),
    "کرمان": (30.2839, 57.0834),
    "یزد": (31.8974, 54.3569),
    "همدان": (34.7983, 48.5146),
    "اردبیل": (38.2498, 48.2933),
    "زاهدان": (29.4963, 60.8629),
    "بندرعباس": (27.1832, 56.2666),
    "ساری": (36.5633, 53.0601),
    "قزوین": (36.2797, 50.0049),
    "خرم‌آباد": (33.4878, 48.3558),
    "سنندج": (35.3219, 46.9862),
    "بوشهر": (28.9234, 50.8203),
    "اراک": (34.0917, 49.6892),
    "زنجان": (36.6736, 48.4787),
    "گرگان": (36.8456, 54.4392),
    "سمنان": (35.5769, 53.3953),
    "بجنورد": (37.4750, 57.3333),
    "ایلام": (33.6374, 46.4226),
    "یاسوج": (30.6684, 51.5879),
    "بیرجند": (32.8663, 59.2211),
    "ساوه": (35.0213, 50.3566),

    # ────────── شهرهای زیارتی عراق ──────────
    "نجف": (31.9996, 44.3147),
    "کربلا": (32.6160, 44.0240),
    "کاظمین": (33.3803, 44.3467),
    "سامرا": (34.1959, 43.8850),
    "بغداد": (33.3152, 44.3661),

    # ────────── نام‌های انگلیسی (برای سازگاری) ──────────
    "tehran": (35.6892, 51.3890),
    "mashhad": (36.2605, 59.6168),
    "isfahan": (32.6546, 51.6680),
    "shiraz": (29.5918, 52.5837),
    "tabriz": (38.0962, 46.2738),
    "qom": (34.6416, 50.8746),
    "karaj": (35.8400, 50.9391),
    "ahvaz": (31.3183, 48.6706),
    "kermanshah": (34.3142, 47.0650),
    "urmia": (37.5527, 45.0761),
    "rasht": (37.2808, 49.5832),
    "kerman": (30.2839, 57.0834),
    "yazd": (31.8974, 54.3569),
    "hamedan": (34.7983, 48.5146),
    "ardabil": (38.2498, 48.2933),
    "zahedan": (29.4963, 60.8629),
    "bandar abbas": (27.1832, 56.2666),
    "sari": (36.5633, 53.0601),
    "qazvin": (36.2797, 50.0049),
    "khorramabad": (33.4878, 48.3558),
    "sanandaj": (35.3219, 46.9862),
    "bushehr": (28.9234, 50.8203),
    "arak": (34.0917, 49.6892),
    "zanjan": (36.6736, 48.4787),
    "gorgan": (36.8456, 54.4392),
    "semnan": (35.5769, 53.3953),
    "bojnurd": (37.4750, 57.3333),
    "ilam": (33.6374, 46.4226),
    "yasuj": (30.6684, 51.5879),
    "birjand": (32.8663, 59.2211),
    "saveh": (35.0213, 50.3566),
    "najaf": (31.9996, 44.3147),
    "karbala": (32.6160, 44.0240),
    "kazimain": (33.3803, 44.3467),
    "samarra": (34.1959, 43.8850),
    "baghdad": (33.3152, 44.3661),
}


def _normalize_city(city: str) -> str:
    """نرمال‌سازی نام شهر برای جستجو در دیکشنری مختصات"""
    if not city:
        return "قم"
    return city.strip().replace("ي", "ی").replace("ك", "ک").lower()


def _get_coords(city: str):
    """برگرداندن (lat, lon) اگر موجود باشد، در غیر این صورت None"""
    if not city:
        return CITY_COORDS.get("قم")
    # جستجوی مستقیم با نام اصلی
    if city.strip() in CITY_COORDS:
        return CITY_COORDS[city.strip()]
    # جستجوی نرمال‌شده
    key = _normalize_city(city)
    if key in CITY_COORDS:
        return CITY_COORDS[key]
    return None


def _parse_timings(timings: dict) -> dict:
    """تبدیل کلیدهای انگلیسی به فارسی"""
    return {
        "اذان صبح": timings["Fajr"],
        "طلوع آفتاب": timings["Sunrise"],
        "اذان ظهر": timings["Dhuhr"],
        "اذان عصر": timings["Asr"],
        "اذان مغرب": timings["Maghrib"],
        "اذان عشاء": timings["Isha"],
    }


def get_prayer_times(city, country="Iran", method=None):
    """
    دریافت اوقات شرعی با اولویت مختصات دقیق.
    اگر مختصات شهر موجود باشد از /timings استفاده می‌کند (دقت بالا)،
    در غیر این صورت به timingsByCity برمی‌گردد.
    """
    method = method if method is not None else config.PRAYER_METHOD
    city = city or "قم"
    key = f"{city}_{country}_{method}"
    now = datetime.now().timestamp()

    if key in _cache_data and now - _cache_time.get(key, 0) < config.CACHE_TTL:
        return _cache_data[key]

    try:
        coords = _get_coords(city)
        if coords:
            lat, lon = coords
            url = (
                f"https://api.aladhan.com/v1/timings"
                f"?latitude={lat}&longitude={lon}"
                f"&method={method}&school=0"
            )
            logger.debug(f"Prayer times via coords for {city}: {lat}, {lon}")
        else:
            # fallback به نام شهر
            url = (
                f"https://api.aladhan.com/v1/timingsByCity"
                f"?city={city}&country={country}"
                f"&method={method}&school=0"
            )
            logger.debug(f"Prayer times via city name for {city}")

        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        timings = data["data"]["timings"]
        result = _parse_timings(timings)

        _cache_data[key] = result
        _cache_time[key] = now
        return result

    except Exception as e:
        logger.error(f"Error fetching prayer times for {city}: {e}")
        return None


def get_next_prayer_time(prayer_times, now_dt):
    """محاسبه زمان باقی‌مانده تا اذان بعدی با کلیدهای فارسی"""
    if not prayer_times:
        return None, None

    prayer_keys = ["اذان صبح", "اذان ظهر", "اذان عصر", "اذان مغرب", "اذان عشاء"]
    today = now_dt.date()
    prayer_datetimes = []

    for key in prayer_keys:
        if key in prayer_times:
            try:
                hour, minute = map(int, prayer_times[key].split(":")[:2])
                dt = datetime.combine(
                    today, datetime.min.time().replace(hour=hour, minute=minute)
                )
                dt = tehran_tz.localize(dt)
                prayer_datetimes.append((key, dt))
            except Exception:
                continue

    if not prayer_datetimes:
        return None, None

    future_prayers = [(key, dt) for key, dt in prayer_datetimes if dt > now_dt]
    if future_prayers:
        next_prayer = min(future_prayers, key=lambda x: x[1])
        return next_prayer[0], next_prayer[1] - now_dt
    else:
        next_day_prayers = [
            (key, dt + timedelta(days=1)) for key, dt in prayer_datetimes
        ]
        next_prayer = min(next_day_prayers, key=lambda x: x[1])
        return next_prayer[0], next_prayer[1] - now_dt


def get_prayer_times_for_date(city, date_str, country="Iran", method=None):
    """
    اوقات شرعی برای یک تاریخ مشخص
    date_str باید به فرمت DD-MM-YYYY باشد
    """
    method = method if method is not None else config.PRAYER_METHOD
    city = city or "قم"
    key = f"{city}_{country}_{date_str}_{method}"
    now = datetime.now().timestamp()

    if key in _cache_data and now - _cache_time.get(key, 0) < config.CACHE_TTL:
        return _cache_data[key]

    try:
        coords = _get_coords(city)
        if coords:
            lat, lon = coords
            url = (
                f"https://api.aladhan.com/v1/timings/{date_str}"
                f"?latitude={lat}&longitude={lon}"
                f"&method={method}&school=0"
            )
        else:
            url = (
                f"https://api.aladhan.com/v1/timingsByCity/{date_str}"
                f"?city={city}&country={country}"
                f"&method={method}&school=0"
            )

        response = requests.get(url, timeout=10)
        response.raise_for_status()
        timings = response.json()["data"]["timings"]
        result = _parse_timings(timings)

        _cache_data[key] = result
        _cache_time[key] = now
        return result

    except Exception as e:
        logger.error(f"prayer for date {date_str} {city}: {e}")
        # fallback به امروز
        return get_prayer_times(city, country=country, method=method)

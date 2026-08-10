"""ابزارها — تبدیل واحد، ماشین‌حساب، پسورد، شمارش متن، یادداشت"""
import re
import random
import string
import secrets

def pn(n):
    return str(n).translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))


# ——— تبدیل واحد ———
LENGTH = {"m": 1, "meter": 1, "متر": 1, "km": 1000, "کیلومتر": 1000, "cm": 0.01, "سانتی‌متر": 0.01, "سانتیمتر": 0.01,
          "mm": 0.001, "mile": 1609.34, "مایل": 1609.34, "yard": 0.9144, "foot": 0.3048, "ft": 0.3048, "inch": 0.0254}
WEIGHT = {"kg": 1, "کیلو": 1, "کیلوگرم": 1, "g": 0.001, "گرم": 0.001, "mg": 1e-6, "ton": 1000, "تن": 1000,
          "lb": 0.453592, "pound": 0.453592, "oz": 0.0283495}
VOLUME = {"l": 1, "liter": 1, "لیتر": 1, "ml": 0.001, "میلی‌لیتر": 0.001, "m3": 1000, "gal": 3.78541}
TEMP = {"c", "f", "k", "سانتیگراد", "فارنهایت", "کلوین", "celsius", "fahrenheit", "kelvin"}


def convert_unit(amount: float, from_u: str, to_u: str) -> str:
    fu, tu = from_u.lower().strip(), to_u.lower().strip()
    # دما
    if fu in TEMP or tu in TEMP:
        return _temp_convert(amount, fu, tu)
    for table, name in ((LENGTH, "طول"), (WEIGHT, "وزن"), (VOLUME, "حجم")):
        if fu in table and tu in table:
            base = amount * table[fu]
            result = base / table[tu]
            return f"📐 **تبدیل {name}**\n\n{pn(amount)} {from_u} = **{pn(f'{result:,.6g}')} {to_u}**"
    return (
        "❌ واحد پشتیبانی نمی‌شود.\n\n"
        "مثال: `10 km m` یا `5 kg g` یا `100 c f`\n"
        "طول: m, km, cm, mile, ft\n"
        "وزن: kg, g, lb, ton\n"
        "حجم: l, ml, gal\n"
        "دما: c, f, k"
    )


def _temp_convert(val, fu, tu):
    # به سلسیوس
    if fu in ("c", "celsius", "سانتیگراد"):
        c = val
    elif fu in ("f", "fahrenheit", "فارنهایت"):
        c = (val - 32) * 5 / 9
    elif fu in ("k", "kelvin", "کلوین"):
        c = val - 273.15
    else:
        return "❌ واحد دما نامعتبر"
    if tu in ("c", "celsius", "سانتیگراد"):
        r = c
    elif tu in ("f", "fahrenheit", "فارنهایت"):
        r = c * 9 / 5 + 32
    elif tu in ("k", "kelvin", "کلوین"):
        r = c + 273.15
    else:
        return "❌ واحد دما نامعتبر"
    return f"🌡 **تبدیل دما**\n\n{pn(val)} {fu} = **{pn(f'{r:,.2f}')} {tu}**"


def parse_unit(text: str):
    t = text.strip().translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789"))
    m = re.match(r"([\d.]+)\s*([a-zA-Zآ-ی‌]+)\s+([a-zA-Zآ-ی‌]+)", t)
    if m:
        return float(m.group(1)), m.group(2), m.group(3)
    return None


def calculator(expr: str) -> str:
    t = expr.translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩×÷", "01234567890123456789*/"))
    t = re.sub(r"[^0-9+\-*/().%\s]", "", t)
    try:
        # امن
        result = eval(t, {"__builtins__": {}}, {})
        return f"🔢 **نتیجه:** {pn(result)}"
    except Exception:
        return "❌ عبارت نامعتبر. مثال: `2+3*4` یا `(10-2)/4`"


def generate_password(length: int = 12) -> str:
    length = max(6, min(64, length))
    alphabet = string.ascii_letters + string.digits + "!@#$%&*"
    pwd = "".join(secrets.choice(alphabet) for _ in range(length))
    return pwd


def count_text(text: str) -> str:
    chars = len(text)
    chars_no_space = len(text.replace(" ", "").replace("\n", ""))
    words = len(text.split())
    lines = text.count("\n") + 1
    return (
        f"📝 **شمارش متن**\n\n"
        f"کاراکتر (با فاصله): {pn(chars)}\n"
        f"کاراکتر (بدون فاصله): {pn(chars_no_space)}\n"
        f"کلمه: {pn(words)}\n"
        f"خط: {pn(lines)}"
    )

# ——— فاصله جهانی (شهر↔شهر / شهر↔کشور) ———
import math
import httpx
from bot.logger import logger

_geo_cache = {}


async def geocode(place: str):
    """جستجوی مختصات مکان (شهر یا کشور) با Nominatim"""
    key = place.strip().lower()
    if not key:
        return None
    if key in _geo_cache:
        return _geo_cache[key]
    try:
        async with httpx.AsyncClient(timeout=10.0, headers={"User-Agent": "ALIMJBot/1.0"}) as client:
            r = await client.get(
                "https://nominatim.openstreetmap.org/search",
                params={
                    "q": place,
                    "format": "json",
                    "limit": 3,
                    "addressdetails": 1,
                },
            )
            data = r.json()
            if not data:
                return None
            # ترجیح: city/town، بعد country
            best = data[0]
            for item in data:
                t = (item.get("type") or "") + " " + (item.get("class") or "")
                if any(x in t for x in ("city", "town", "village", "municipality", "province", "state")):
                    best = item
                    break
            lat, lon = float(best["lat"]), float(best["lon"])
            name = best.get("display_name", place)
            # کوتاه‌کردن نام
            parts = [x.strip() for x in name.split(",")]
            short = ", ".join(parts[:3]) if len(parts) > 3 else name
            _geo_cache[key] = (lat, lon, short)
            return lat, lon, short
    except Exception as e:
        logger.error(f"geocode [{place}]: {e}")
    return None


def haversine(lat1, lon1, lat2, lon2):
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    )
    return R * 2 * math.asin(math.sqrt(min(1.0, a)))


def _fmt_duration(hours: float) -> str:
    if hours < 0.01:
        return "کمتر از ۱ دقیقه"
    if hours < 1:
        return f"{int(hours * 60)} دقیقه"
    h = int(hours)
    m = int((hours - h) * 60)
    if h >= 24:
        d = h // 24
        h2 = h % 24
        return f"{d} روز و {h2} ساعت" if h2 else f"{d} روز"
    return f"{h} ساعت و {m} دقیقه" if m else f"{h} ساعت"


def parse_two_places(text: str):
    """پارس دو مکان از متن کاربر
    پشتیبانی:
      تهران مشهد
      تهران تا استانبول
      تهران - ترکیه
      Paris to Tokyo
      تهران، آلمان
    """
    t = text.strip()
    if not t:
        return None
    # جداکننده‌های رایج
    for sep in [" تا ", " to ", " - ", " – ", " — ", "،", ",", "\t"]:
        if sep in t:
            parts = [p.strip() for p in t.split(sep, 1)]
            if len(parts) == 2 and parts[0] and parts[1]:
                return parts[0], parts[1]
    parts = t.split()
    if len(parts) >= 2:
        # اگر ۳+ کلمه: نصف کن
        mid = len(parts) // 2
        return " ".join(parts[:mid]), " ".join(parts[mid:])
    return None


async def world_distance(place1: str, place2: str = None) -> str:
    """فاصله شهر به شهر یا شهر به کشور یا کشور به کشور"""
    if place2 is None:
        parsed = parse_two_places(place1)
        if not parsed:
            return (
                "❌ فرمت درست نیست.\n\n"
                "مثال‌ها:\n"
                "• `تهران مشهد`\n"
                "• `تهران تا استانبول`\n"
                "• `شیراز آلمان`\n"
                "• `Paris to Tokyo`\n"
                "• `اصفهان - ترکیه`"
            )
        place1, place2 = parsed

    g1 = await geocode(place1)
    g2 = await geocode(place2)
    if not g1:
        return f"❌ «{place1}» پیدا نشد.\nنام شهر یا کشور را دقیق‌تر بنویسید."
    if not g2:
        return f"❌ «{place2}» پیدا نشد.\nنام شهر یا کشور را دقیق‌تر بنویسید."

    lat1, lon1, n1 = g1
    lat2, lon2, n2 = g2
    km = haversine(lat1, lon1, lat2, lon2)

    car = km / 80
    bike = km / 18
    walk = km / 5
    plane = (km / 800) + 0.5

    return (
        f"🗺 فاصله جهانی\n\n"
        f"از: {n1}\n"
        f"تا: {n2}\n\n"
        f"📏 فاصله مستقیم: {pn(f'{km:,.1f}')} کیلومتر\n\n"
        f"🚗 خودرو (≈۸۰km/h): {_fmt_duration(car)}\n"
        f"🚲 دوچرخه (≈۱۸km/h): {_fmt_duration(bike)}\n"
        f"🚶 پیاده (≈۵km/h): {_fmt_duration(walk)}\n"
        f"✈️ هواپیما (تقریبی): {_fmt_duration(plane)}\n\n"
        f"⚠️ فاصله خط مستقیم است؛ مسیر واقعی جاده‌ای ممکن است بیشتر باشد."
    )

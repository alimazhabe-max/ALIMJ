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


# ——— فاصله جهانی ———
import math
import httpx
from bot.logger import logger

_geo_cache = {}


async def geocode(place: str):
    key = place.strip().lower()
    if key in _geo_cache:
        return _geo_cache[key]
    try:
        async with httpx.AsyncClient(timeout=8.0, headers={"User-Agent": "ALIMJBot/1.0"}) as c:
            r = await c.get(
                "https://nominatim.openstreetmap.org/search",
                params={"q": place, "format": "json", "limit": 1},
            )
            data = r.json()
            if data:
                lat, lon = float(data[0]["lat"]), float(data[0]["lon"])
                name = data[0].get("display_name", place)[:60]
                _geo_cache[key] = (lat, lon, name)
                return lat, lon, name
    except Exception as e:
        logger.error(f"geocode: {e}")
    return None


def haversine(lat1, lon1, lat2, lon2):
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return R * 2 * math.asin(math.sqrt(a))


def _fmt_duration(hours: float) -> str:
    if hours < 1:
        return f"{int(hours * 60)} دقیقه"
    h = int(hours)
    m = int((hours - h) * 60)
    if h >= 24:
        d = h // 24
        h = h % 24
        return f"{d} روز و {h} ساعت"
    return f"{h} ساعت و {m} دقیقه" if m else f"{h} ساعت"


async def world_distance(place1: str, place2: str) -> str:
    g1 = await geocode(place1)
    g2 = await geocode(place2)
    if not g1:
        return f"❌ مکان «{place1}» پیدا نشد. نام شهر/کشور را دقیق‌تر بنویسید."
    if not g2:
        return f"❌ مکان «{place2}» پیدا نشد."
    lat1, lon1, n1 = g1
    lat2, lon2, n2 = g2
    km = haversine(lat1, lon1, lat2, lon2)
    # سرعت تقریبی
    car = km / 80
    bike = km / 18
    walk = km / 5
    plane = km / 800 + 0.5  # + نیم‌ساعت فرودگاه
    return (
        f"🗺 **فاصله جهانی**\n\n"
        f"از: {n1}\n"
        f"تا: {n2}\n\n"
        f"📏 فاصله مستقیم: **{pn(f'{km:,.1f}')} کیلومتر**\n\n"
        f"🚗 با خودرو (≈۸۰km/h): {_fmt_duration(car)}\n"
        f"🚲 با دوچرخه (≈۱۸km/h): {_fmt_duration(bike)}\n"
        f"🚶 پیاده (≈۵km/h): {_fmt_duration(walk)}\n"
        f"✈️ هواپیما (تقریبی): {_fmt_duration(plane)}\n\n"
        f"⚠️ فاصله هوایی مستقیم است؛ مسیر واقعی ممکن است بیشتر باشد."
    )

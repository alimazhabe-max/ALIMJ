"""ابزارها — تبدیل واحد، ماشین‌حساب، پسورد، شمارش متن، فاصله جهانی"""
import re
import math
import asyncio
import secrets
import string
import httpx
from bot.logger import logger


def pn(n):
    return str(n).translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))


LENGTH = {
    "m": 1, "meter": 1, "meters": 1, "متر": 1, "م": 1,
    "km": 1000, "کیلومتر": 1000,
    "cm": 0.01, "سانتی‌متر": 0.01, "سانتیمتر": 0.01, "سانت": 0.01,
    "mm": 0.001, "میلی‌متر": 0.001, "میلیمتر": 0.001,
    "mile": 1609.34, "miles": 1609.34, "مایل": 1609.34,
    "yard": 0.9144, "foot": 0.3048, "ft": 0.3048, "feet": 0.3048,
    "inch": 0.0254, "in": 0.0254,
}
WEIGHT = {
    "kg": 1, "کیلو": 1, "کیلوگرم": 1,
    "g": 0.001, "gram": 0.001, "گرم": 0.001,
    "mg": 1e-6, "ton": 1000, "تن": 1000, "t": 1000,
    "lb": 0.453592, "pound": 0.453592, "oz": 0.0283495,
}
VOLUME = {
    "l": 1, "liter": 1, "litre": 1, "لیتر": 1,
    "ml": 0.001, "میلی‌لیتر": 0.001, "میلیلیتر": 0.001,
    "m3": 1000, "gal": 3.78541, "gallon": 3.78541,
}
TEMP = {"c", "f", "k", "سانتیگراد", "فارنهایت", "کلوین", "celsius", "fahrenheit", "kelvin"}


def convert_unit(amount: float, from_u: str, to_u: str) -> str:
    fu, tu = from_u.lower().strip(), to_u.lower().strip()
    if fu in TEMP or tu in TEMP:
        return _temp_convert(amount, fu, tu) + "\n\n🔗 تبدیل‌های بیشتر: https://www.bahesab.ir/calc/unit/"
    for table, name in ((LENGTH, "طول"), (WEIGHT, "وزن"), (VOLUME, "حجم")):
        if fu in table and tu in table:
            result = amount * table[fu] / table[tu]
            return (
                f"📐 تبدیل {name}\n\n"
                f"{pn(amount)} {from_u} = {pn(f'{result:,.6g}')} {to_u}\n\n"
                f"🔗 تبدیل واحدهای بیشتر و دقیق‌تر:\nhttps://www.bahesab.ir/calc/unit/"
            )
    return (
        "❌ واحد پشتیبانی نمی‌شود.\n\n"
        "مثال:\n10 km m\n5 kg g\n100 c f\n"
        "طول: m km cm mile ft\nوزن: kg g lb\nحجم: l ml\nدما: c f k\n\n"
        "🔗 برای همه واحدها به سایت باحساب مراجعه کنید:\n"
        "https://www.bahesab.ir/calc/unit/"
    )


def _temp_convert(val, fu, tu):
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
    return f"🌡 تبدیل دما\n\n{pn(val)} {fu} = {pn(f'{r:,.2f}')} {tu}"


def parse_unit(text: str):
    t = text.strip().translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789"))
    t = t.replace(" به ", " ").replace(" to ", " ").replace("->", " ").replace("→", " ")
    m = re.match(r"([\d.]+)\s*([a-zA-Zآ-ی‌]+)\s+([a-zA-Zآ-ی‌]+)", t)
    if m:
        return float(m.group(1)), m.group(2).lower(), m.group(3).lower()
    m = re.match(r"([\d.]+)\s*([a-zA-Z]+)\s*([a-zA-Z]+)", t)
    if m:
        return float(m.group(1)), m.group(2).lower(), m.group(3).lower()
    return None


def calculator(expr: str) -> str:
    t = expr.translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩×÷", "01234567890123456789*/"))
    t = re.sub(r"[^0-9+\-*/().%\s]", "", t)
    try:
        result = eval(t, {"__builtins__": {}}, {})
        return f"🔢 نتیجه: {pn(result)}"
    except Exception:
        return "❌ عبارت نامعتبر. مثال: 2+3*4"


def generate_password(length: int = 16) -> str:
    length = max(6, min(64, length))
    alphabet = string.ascii_letters + string.digits + "!@#$%&*"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def count_text(text: str) -> str:
    chars = len(text)
    chars_no_space = len(text.replace(" ", "").replace("\n", ""))
    words = len(text.split())
    lines = text.count("\n") + 1
    return (
        f"📝 شمارش متن\n\n"
        f"کاراکتر (با فاصله): {pn(chars)}\n"
        f"کاراکتر (بدون فاصله): {pn(chars_no_space)}\n"
        f"کلمه: {pn(words)}\n"
        f"خط: {pn(lines)}"
    )


# ——— فاصله جهانی ———
_geo_cache = {}

# مکان‌های معروف مذهبی و شهری (اولویت بالاتر از جستجوی عمومی)
# (lat, lon, "شهر، کشور")
KNOWN_PLACES = {
    # ایران
    "تهران": (35.6892, 51.3890, "تهران، ایران"),
    "tehran": (35.6892, 51.3890, "تهران، ایران"),
    "قم": (34.6416, 50.8746, "قم، ایران"),
    "qom": (34.6416, 50.8746, "قم، ایران"),
    "مشهد": (36.2605, 59.6168, "مشهد، ایران"),
    "mashhad": (36.2605, 59.6168, "مشهد، ایران"),
    "اصفهان": (32.6546, 51.6680, "اصفهان، ایران"),
    "isfahan": (32.6546, 51.6680, "اصفهان، ایران"),
    "شیراز": (29.5918, 52.5837, "شیراز، ایران"),
    "shiraz": (29.5918, 52.5837, "شیراز، ایران"),
    "تبریز": (38.0962, 46.2738, "تبریز، ایران"),
    "اهواز": (31.3183, 48.6706, "اهواز، ایران"),
    "کرمان": (30.2832, 57.0788, "کرمان، ایران"),
    "یزد": (31.8974, 54.3569, "یزد، ایران"),
    "رشت": (37.2808, 49.5832, "رشت، ایران"),
    "کرج": (35.8400, 50.9391, "کرج، ایران"),
    "همدان": (34.7992, 48.5146, "همدان، ایران"),
    "ارومیه": (37.5527, 45.0761, "ارومیه، ایران"),
    "کرمانشاه": (34.3142, 47.0650, "کرمانشاه، ایران"),
    "بندرعباس": (27.1832, 56.2666, "بندرعباس، ایران"),
    "زاهدان": (29.4963, 60.8629, "زاهدان، ایران"),
    "ساری": (36.5633, 53.0601, "ساری، ایران"),
    "اردبیل": (38.2498, 48.2933, "اردبیل، ایران"),
    "بوشهر": (28.9234, 50.8203, "بوشهر، ایران"),
    "خرم‌آباد": (33.4878, 48.3558, "خرم‌آباد، ایران"),
    "خرم اباد": (33.4878, 48.3558, "خرم‌آباد، ایران"),
    "سنندج": (35.3219, 46.9862, "سنندج، ایران"),
    "قزوین": (36.2797, 50.0049, "قزوین، ایران"),
    "زنجان": (36.6769, 48.4963, "زنجان، ایران"),
    "گرگان": (36.8456, 54.4393, "گرگان، ایران"),
    "ایلام": (33.6374, 46.4227, "ایلام، ایران"),
    "شهرکرد": (32.3256, 50.8644, "شهرکرد، ایران"),
    "یاسوج": (30.6684, 51.5876, "یاسوج، ایران"),
    "بیرجند": (32.8663, 59.2211, "بیرجند، ایران"),
    "بجنورد": (37.4747, 57.3290, "بجنورد، ایران"),
    "سمنان": (35.5769, 53.3953, "سمنان، ایران"),
    # عراق — شهرهای مذهبی
    "کربلا": (32.6160, 44.0240, "کربلا، عراق"),
    "کربلاء": (32.6160, 44.0240, "کربلا، عراق"),
    "karbala": (32.6160, 44.0240, "کربلا، عراق"),
    "karbala iraq": (32.6160, 44.0240, "کربلا، عراق"),
    "نجف": (31.9996, 44.3333, "نجف، عراق"),
    "النجف": (31.9996, 44.3333, "نجف، عراق"),
    "najaf": (31.9996, 44.3333, "نجف، عراق"),
    "بغداد": (33.3152, 44.3661, "بغداد، عراق"),
    "baghdad": (33.3152, 44.3661, "بغداد، عراق"),
    "کاظمین": (33.3803, 44.3419, "کاظمین، عراق"),
    "کاظمیه": (33.3803, 44.3419, "کاظمین، عراق"),
    "سامرا": (34.1959, 43.8730, "سامرا، عراق"),
    "samarra": (34.1959, 43.8730, "سامرا، عراق"),
    "بصره": (30.5081, 47.7835, "بصره، عراق"),
    "basra": (30.5081, 47.7835, "بصره، عراق"),
    "موصل": (36.3350, 43.1189, "موصل، عراق"),
    "اربيل": (36.1911, 44.0094, "اربیل، عراق"),
    "اربیل": (36.1911, 44.0094, "اربیل، عراق"),
    # عربستان
    "مکه": (21.4225, 39.8262, "مکه، عربستان"),
    "مکه مکرمه": (21.4225, 39.8262, "مکه، عربستان"),
    "mecca": (21.4225, 39.8262, "مکه، عربستان"),
    "مدینه": (24.4672, 39.6111, "مدینه، عربستان"),
    "مدینه منوره": (24.4672, 39.6111, "مدینه، عربستان"),
    "medina": (24.4672, 39.6111, "مدینه، عربستان"),
    "ریاض": (24.7136, 46.6753, "ریاض، عربستان"),
    "jeddah": (21.4858, 39.1925, "جدة، عربستان"),
    "جده": (21.4858, 39.1925, "جدة، عربستان"),
    # سوریه
    "دمشق": (33.5138, 36.2765, "دمشق، سوریه"),
    "damascus": (33.5138, 36.2765, "دمشق، سوریه"),
    "حلب": (36.2021, 37.1343, "حلب، سوریه"),
    # لبنان
    "بیروت": (33.8938, 35.5018, "بیروت، لبنان"),
    "beirut": (33.8938, 35.5018, "بیروت، لبنان"),
    # ترکیه
    "استانبول": (41.0082, 28.9784, "استانبول، ترکیه"),
    "istanbul": (41.0082, 28.9784, "استانبول، ترکیه"),
    "آنکارا": (39.9334, 32.8597, "آنکارا، ترکیه"),
    "آنکارا": (39.9334, 32.8597, "آنکارا، ترکیه"),
    # امارات
    "دبی": (25.2048, 55.2708, "دبی، امارات"),
    "dubai": (25.2048, 55.2708, "دبی، امارات"),
    "ابوظبی": (24.4539, 54.3773, "ابوظبی، امارات"),
    # افغانستان
    "کابل": (34.5553, 69.2075, "کابل، افغانستان"),
    "kabul": (34.5553, 69.2075, "کابل، افغانستان"),
    "هرات": (34.3482, 62.1997, "هرات، افغانستان"),
    "مشهد اردهال": (34.0000, 51.0833, "مشهد اردهال، ایران"),
}


def _short_name(display_name: str, place_hint: str = "") -> str:
    """فقط شهر و کشور را نگه دار — بقیه را حذف کن"""
    if not display_name:
        return place_hint or "?"
    parts = [p.strip() for p in str(display_name).split(",") if p.strip()]
    if not parts:
        return place_hint or "?"
    # حذف بخش‌های اضافی مثل «بخش مرکزی»، «استان»، شماره و ...
    skip_words = (
        "بخش", "شهرستان", "استان", "دهستان", "روستا", "محله", "منطقه",
        "county", "province", "district", "village", "region", "oblast",
        "governorate", "municipality", "state of",
    )
    cleaned = []
    for p in parts:
        low = p.lower()
        if any(sw in low for sw in skip_words):
            continue
        # رد کردن چیزهایی که فقط عدد یا خیلی کوتاه‌اند
        if re.match(r"^[\d\s\-]+$", p):
            continue
        cleaned.append(p)
    if not cleaned:
        cleaned = parts[:2]
    # حداکثر ۲ بخش: شهر + کشور
    if len(cleaned) >= 2:
        return f"{cleaned[0]}، {cleaned[-1]}"
    return cleaned[0]


async def geocode(place: str):
    """
    تبدیل نام مکان به مختصات.
    اولویت: لیست مکان‌های معروف → Google Maps → Nominatim → Photon
    نمایش فقط: شهر، کشور
    """
    place = (place or "").strip()
    if not place:
        return None
    key = place.lower().strip()
    if key in _geo_cache:
        return _geo_cache[key]

    # ۱) مکان‌های معروف از پیش تعریف‌شده
    if key in KNOWN_PLACES:
        lat, lon, short = KNOWN_PLACES[key]
        _geo_cache[key] = (lat, lon, short)
        return lat, lon, short
    # جستجوی تقریبی در کلیدها
    for k, v in KNOWN_PLACES.items():
        if key == k or key in k or k in key:
            lat, lon, short = v
            _geo_cache[key] = (lat, lon, short)
            return lat, lon, short

    headers = {"User-Agent": "ALIMJBot/2.1 (telegram-bot)"}
    try:
        from bot.config import config
        async with httpx.AsyncClient(timeout=15.0, headers=headers, follow_redirects=True) as client:
            data = []

            # ۲) Google Maps Geocoding API
            gkey = getattr(config, "GOOGLE_MAPS_API_KEY", "") or ""
            if gkey:
                try:
                    r = await client.get(
                        "https://maps.googleapis.com/maps/api/geocode/json",
                        params={"address": place, "key": gkey, "language": "fa"},
                    )
                    if r.status_code == 200:
                        js = r.json() or {}
                        if js.get("status") == "OK" and js.get("results"):
                            res = js["results"][0]
                            loc = res.get("geometry", {}).get("location") or {}
                            lat = float(loc.get("lat", 0))
                            lon = float(loc.get("lng", 0))
                            name = res.get("formatted_address") or place
                            short = _short_name(name, place)
                            _geo_cache[key] = (lat, lon, short)
                            return lat, lon, short
                except Exception as e:
                    logger.warning(f"Google geocode [{place}]: {e}")

            # ۳) Nominatim — با اولویت به شهر/کشور و importance بالاتر
            queries = [place]
            # برای نام‌های عربی/مذهبی، نسخه انگلیسی هم امتحان کن
            en_map = {
                "کربلا": "Karbala, Iraq",
                "کربلاء": "Karbala, Iraq",
                "نجف": "Najaf, Iraq",
                "مکه": "Mecca, Saudi Arabia",
                "مدینه": "Medina, Saudi Arabia",
                "کاظمین": "Kadhimiya, Iraq",
                "سامرا": "Samarra, Iraq",
            }
            if place in en_map:
                queries.insert(0, en_map[place])
            queries.append(f"{place}, Iran")

            for q in queries:
                try:
                    r = await client.get(
                        "https://nominatim.openstreetmap.org/search",
                        params={
                            "q": q,
                            "format": "json",
                            "limit": 8,
                            "accept-language": "fa,en",
                            "featuretype": "city",
                        },
                    )
                    if r.status_code == 200:
                        results = r.json() or []
                        if results:
                            # ترجیح: type=city/town/administrative با importance بالاتر
                            def score(item):
                                t = (item.get("type") or "").lower()
                                cls = (item.get("class") or "").lower()
                                imp = float(item.get("importance") or 0)
                                bonus = 0
                                if t in ("city", "town", "municipality", "administrative"):
                                    bonus += 2
                                if cls in ("place", "boundary"):
                                    bonus += 1
                                # جریمه برای نتایج خیلی جزئی
                                dn = (item.get("display_name") or "").lower()
                                if any(x in dn for x in ("بخش", "روستا", "دهستان", "village", "hamlet")):
                                    bonus -= 3
                                return imp + bonus
                            results.sort(key=score, reverse=True)
                            data = results
                            break
                except Exception:
                    pass

            # ۴) Photon fallback
            if not data:
                try:
                    r = await client.get(
                        "https://photon.komoot.io/api/",
                        params={"q": place, "limit": 5},
                    )
                    if r.status_code == 200:
                        for f in (r.json() or {}).get("features") or []:
                            coords = f.get("geometry", {}).get("coordinates") or []
                            props = f.get("properties") or {}
                            if len(coords) >= 2:
                                nm = props.get("name") or place
                                country = props.get("country") or ""
                                city = props.get("city") or props.get("state") or ""
                                if city and country:
                                    display = f"{city}, {country}"
                                elif country:
                                    display = f"{nm}, {country}"
                                else:
                                    display = nm
                                data.append({"lat": coords[1], "lon": coords[0], "display_name": display})
                except Exception:
                    pass

            if not data:
                return None
            best = data[0]
            lat = float(best["lat"])
            lon = float(best["lon"])
            name = best.get("display_name") or place
            short = _short_name(name, place)
            _geo_cache[key] = (lat, lon, short)
            return lat, lon, short
    except Exception as e:
        logger.error(f"geocode [{place}]: {e}")
    return None


def haversine(lat1, lon1, lat2, lon2):
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return R * 2 * math.asin(math.sqrt(min(1.0, a)))


def _fmt_duration(hours: float) -> str:
    if hours < 0.01:
        return "کمتر از ۱ دقیقه"
    if hours < 1:
        return f"{int(hours * 60)} دقیقه"
    h = int(hours)
    m = int((hours - h) * 60)
    if h >= 24:
        d, h2 = h // 24, h % 24
        return f"{d} روز و {h2} ساعت" if h2 else f"{d} روز"
    return f"{h} ساعت و {m} دقیقه" if m else f"{h} ساعت"


def parse_two_places(text: str):
    t = (text or "").strip()
    if not t:
        return None
    for sep in [" تا ", " to ", " - ", " – ", " — ", "،", ",", "\t", " -> ", " → "]:
        if sep in t:
            a, b = [p.strip() for p in t.split(sep, 1)]
            if a and b:
                return a, b
    parts = t.split()
    if len(parts) >= 2:
        mid = len(parts) // 2
        return " ".join(parts[:mid]), " ".join(parts[mid:])
    return None


async def world_distance(place1: str, place2: str = None) -> str:
    if place2 is None:
        parsed = parse_two_places(place1)
        if not parsed:
            return (
                "❌ دو مکان بنویسید.\n\n"
                "مثال:\nتهران مشهد\nتهران تا ترکیه\nParis to Tokyo\nNew York to London"
            )
        place1, place2 = parsed

    g1, g2 = await asyncio.gather(geocode(place1), geocode(place2))
    if not g1:
        return f"❌ «{place1}» پیدا نشد.\nنام شهر یا کشور را فارسی یا انگلیسی بنویسید (همه شهرها و کشورها پشتیبانی می‌شوند)."
    if not g2:
        return f"❌ «{place2}» پیدا نشد.\nنام شهر یا کشور را فارسی یا انگلیسی بنویسید (همه شهرها و کشورها پشتیبانی می‌شوند)."

    lat1, lon1, n1 = g1
    lat2, lon2, n2 = g2
    km = haversine(lat1, lon1, lat2, lon2)

    # اگر کلید Google موجود باشد، فاصله و زمان واقعی رانندگی را هم بگیر
    driving_info = ""
    try:
        from bot.config import config
        gkey = getattr(config, "GOOGLE_MAPS_API_KEY", "") or ""
        if gkey:
            async with httpx.AsyncClient(timeout=12.0) as client:
                r = await client.get(
                    "https://maps.googleapis.com/maps/api/distancematrix/json",
                    params={
                        "origins": f"{lat1},{lon1}",
                        "destinations": f"{lat2},{lon2}",
                        "mode": "driving",
                        "language": "fa",
                        "units": "metric",
                        "key": gkey,
                    },
                )
                if r.status_code == 200:
                    js = r.json() or {}
                    el = ((js.get("rows") or [{}])[0].get("elements") or [{}])[0]
                    if el.get("status") == "OK":
                        dist_txt = (el.get("distance") or {}).get("text", "")
                        dur_txt = (el.get("duration") or {}).get("text", "")
                        if dist_txt or dur_txt:
                            driving_info = f"\n🚗 فاصله جاده‌ای (گوگل مپ): {dist_txt} — زمان تقریبی: {dur_txt}\n"
    except Exception as e:
        logger.warning(f"Distance Matrix: {e}")

    return (
        f"🗺 فاصله جهانی\n\n"
        f"از: {n1}\n"
        f"تا: {n2}\n\n"
        f"📏 فاصله مستقیم (خط هوایی): {pn(f'{km:,.1f}')} کیلومتر\n"
        f"{driving_info}"
        f"\n🚗 خودرو (تقریبی): {_fmt_duration(km / 80)}\n"
        f"🚲 دوچرخه: {_fmt_duration(km / 18)}\n"
        f"🚶 پیاده: {_fmt_duration(km / 5)}\n"
        f"✈️ هواپیما: {_fmt_duration(km / 800 + 0.5)}\n\n"
        f"✅ پشتیبانی از همه شهرها و کشورهای جهان"
    )

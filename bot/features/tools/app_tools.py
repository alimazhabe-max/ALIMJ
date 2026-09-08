"""ابزارها — ماشین‌حساب، پسورد، شمارش متن، فاصله جهانی"""
import re
import math
import asyncio
import secrets
import string
import httpx
from bot.logger import logger


def pn(n):
    return str(n).translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))


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

# مکان‌های از پیش‌تعریف‌شده: کلید normalized → (lat, lon, "نمایش")
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
    "esfahan": (32.6546, 51.6680, "اصفهان، ایران"),
    "شیراز": (29.5918, 52.5837, "شیراز، ایران"),
    "shiraz": (29.5918, 52.5837, "شیراز، ایران"),
    "تبریز": (38.0962, 46.2738, "تبریز، ایران"),
    "tabriz": (38.0962, 46.2738, "تبریز، ایران"),
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
    "خرم آباد": (33.4878, 48.3558, "خرم‌آباد، ایران"),
    "خرم‌آباد": (33.4878, 48.3558, "خرم‌آباد، ایران"),
    "سنندج": (35.3219, 46.9862, "سنندج، ایران"),
    "قزوین": (36.2797, 50.0049, "قزوین، ایران"),
    "زنجان": (36.6769, 48.4963, "زنجان، ایران"),
    "گرگان": (36.8427, 54.4439, "گرگان، ایران"),
    "ایلام": (33.6374, 46.4227, "ایلام، ایران"),
    "شهرکرد": (32.3256, 50.8644, "شهرکرد، ایران"),
    "یاسوج": (30.6684, 51.5876, "یاسوج، ایران"),
    "بیرجند": (32.8663, 59.2211, "بیرجند، ایران"),
    "بجنورد": (37.4747, 57.3290, "بجنورد، ایران"),
    "سمنان": (35.5769, 53.3953, "سمنان، ایران"),
    "کیش": (26.5570, 53.9800, "کیش، ایران"),
    "قشم": (26.9581, 56.2719, "قشم، ایران"),
    # عراق
    "کربلا": (32.6160, 44.0240, "کربلا، عراق"),
    "کربلاء": (32.6160, 44.0240, "کربلا، عراق"),
    "karbala": (32.6160, 44.0240, "کربلا، عراق"),
    "نجف": (31.9996, 44.3333, "نجف، عراق"),
    "najaf": (31.9996, 44.3333, "نجف، عراق"),
    "بغداد": (33.3152, 44.3661, "بغداد، عراق"),
    "baghdad": (33.3152, 44.3661, "بغداد، عراق"),
    "کاظمین": (33.3803, 44.3419, "کاظمین، عراق"),
    "سامرا": (34.1959, 43.8730, "سامرا، عراق"),
    "بصره": (30.5081, 47.7835, "بصره، عراق"),
    "موصل": (36.3350, 43.1189, "موصل، عراق"),
    "اربیل": (36.1911, 44.0094, "اربیل، عراق"),
    # عربستان
    "مکه": (21.4225, 39.8262, "مکه، عربستان"),
    "مکه مکرمه": (21.4225, 39.8262, "مکه، عربستان"),
    "mecca": (21.4225, 39.8262, "مکه، عربستان"),
    "مدینه": (24.4672, 39.6111, "مدینه، عربستان"),
    "مدینه منوره": (24.4672, 39.6111, "مدینه، عربستان"),
    "medina": (24.4672, 39.6111, "مدینه، عربستان"),
    "ریاض": (24.7136, 46.6753, "ریاض، عربستان"),
    "جده": (21.4858, 39.1925, "جده، عربستان"),
    "jeddah": (21.4858, 39.1925, "جده، عربستان"),
    # منطقه
    "دمشق": (33.5138, 36.2765, "دمشق، سوریه"),
    "حلب": (36.2021, 37.1343, "حلب، سوریه"),
    "بیروت": (33.8938, 35.5018, "بیروت، لبنان"),
    "استانبول": (41.0082, 28.9784, "استانبول، ترکیه"),
    "istanbul": (41.0082, 28.9784, "استانبول، ترکیه"),
    "آنکارا": (39.9334, 32.8597, "آنکارا، ترکیه"),
    "ankara": (39.9334, 32.8597, "آنکارا، ترکیه"),
    "دبی": (25.2048, 55.2708, "دبی، امارات"),
    "dubai": (25.2048, 55.2708, "دبی، امارات"),
    "ابوظبی": (24.4539, 54.3773, "ابوظبی، امارات"),
    "کابل": (34.5553, 69.2075, "کابل، افغانستان"),
    "هرات": (34.3482, 62.1997, "هرات، افغانستان"),
    # جهان
    "پاریس": (48.8566, 2.3522, "پاریس، فرانسه"),
    "paris": (48.8566, 2.3522, "پاریس، فرانسه"),
    "لندن": (51.5074, -0.1278, "لندن، انگلیس"),
    "london": (51.5074, -0.1278, "لندن، انگلیس"),
    "نیویورک": (40.7128, -74.0060, "نیویورک، آمریکا"),
    "new york": (40.7128, -74.0060, "نیویورک، آمریکا"),
    "tokyo": (35.6762, 139.6503, "توکیو، ژاپن"),
    "توکیو": (35.6762, 139.6503, "توکیو، ژاپن"),
    "مسکو": (55.7558, 37.6173, "مسکو، روسیه"),
    "moscow": (55.7558, 37.6173, "مسکو، روسیه"),
    "پکن": (39.9042, 116.4074, "پکن، چین"),
    "beijing": (39.9042, 116.4074, "پکن، چین"),
    "دهلی": (28.6139, 77.2090, "دهلی نو، هند"),
    "سیدنی": (-33.8688, 151.2093, "سیدنی، استرالیا"),
    "sydney": (-33.8688, 151.2093, "سیدنی، استرالیا"),
    "تورنتو": (43.6532, -79.3832, "تورنتو، کانادا"),
    "برلین": (52.5200, 13.4050, "برلین، آلمان"),
    "berlin": (52.5200, 13.4050, "برلین، آلمان"),
    "مادرید": (40.4168, -3.7038, "مادرید، اسپانیا"),
    "رم": (41.9028, 12.4964, "رم، ایتالیا"),
    "rome": (41.9028, 12.4964, "رم، ایتالیا"),
    "قاهره": (30.0444, 31.2357, "قاهره، مصر"),
    "cairo": (30.0444, 31.2357, "قاهره، مصر"),
}

# کشورها → مرکز/پایتخت تقریبی
COUNTRY_CENTERS = {
    "ایران": (32.4279, 53.6880, "ایران (مرکز)"),
    "iran": (32.4279, 53.6880, "ایران (مرکز)"),
    "ترکیه": (39.9334, 32.8597, "ترکیه (آنکارا)"),
    "turkey": (39.9334, 32.8597, "ترکیه (آنکارا)"),
    "عراق": (33.3152, 44.3661, "عراق (بغداد)"),
    "iraq": (33.3152, 44.3661, "عراق (بغداد)"),
    "عربستان": (24.7136, 46.6753, "عربستان (ریاض)"),
    "saudi arabia": (24.7136, 46.6753, "عربستان (ریاض)"),
    "امارات": (25.2048, 55.2708, "امارات (دبی)"),
    "آمریکا": (38.9072, -77.0369, "آمریکا (واشنگتن)"),
    "usa": (38.9072, -77.0369, "آمریکا (واشنگتن)"),
    "united states": (38.9072, -77.0369, "آمریکا (واشنگتن)"),
    "چین": (39.9042, 116.4074, "چین (پکن)"),
    "china": (39.9042, 116.4074, "چین (پکن)"),
    "روسیه": (55.7558, 37.6173, "روسیه (مسکو)"),
    "russia": (55.7558, 37.6173, "روسیه (مسکو)"),
    "هند": (28.6139, 77.2090, "هند (دهلی)"),
    "india": (28.6139, 77.2090, "هند (دهلی)"),
    "آلمان": (52.5200, 13.4050, "آلمان (برلین)"),
    "germany": (52.5200, 13.4050, "آلمان (برلین)"),
    "فرانسه": (48.8566, 2.3522, "فرانسه (پاریس)"),
    "france": (48.8566, 2.3522, "فرانسه (پاریس)"),
    "انگلیس": (51.5074, -0.1278, "انگلیس (لندن)"),
    "england": (51.5074, -0.1278, "انگلیس (لندن)"),
    "uk": (51.5074, -0.1278, "انگلیس (لندن)"),
    "ژاپن": (35.6762, 139.6503, "ژاپن (توکیو)"),
    "japan": (35.6762, 139.6503, "ژاپن (توکیو)"),
    "افغانستان": (34.5553, 69.2075, "افغانستان (کابل)"),
    "پاکستان": (33.6844, 73.0479, "پاکستان (اسلام‌آباد)"),
    "سوریه": (33.5138, 36.2765, "سوریه (دمشق)"),
    "لبنان": (33.8938, 35.5018, "لبنان (بیروت)"),
}


def _norm_place(s: str) -> str:
    s = (s or "").strip()
    s = s.replace("ي", "ی").replace("ك", "ک").replace("‌", " ").replace("  ", " ")
    return s.strip().lower()


def _short_name(display_name: str, place_hint: str = "") -> str:
    if not display_name:
        return place_hint or "?"
    parts = [p.strip() for p in str(display_name).split(",") if p.strip()]
    if not parts:
        return place_hint or "?"
    skip = ("بخش", "شهرستان", "استان", "دهستان", "روستا", "county", "province",
            "district", "village", "region", "oblast", "governorate", "municipality")
    cleaned = []
    for p in parts:
        low = p.lower()
        if any(sw in low for sw in skip):
            continue
        if re.match(r"^[\d\s\-]+$", p):
            continue
        cleaned.append(p)
    if not cleaned:
        cleaned = parts[:2]
    if len(cleaned) >= 2:
        return f"{cleaned[0]}، {cleaned[-1]}"
    return cleaned[0]


async def geocode(place: str):
    """(lat, lon, display_name) یا None"""
    place_raw = (place or "").strip()
    if not place_raw:
        return None
    key = _norm_place(place_raw)
    if key in _geo_cache:
        return _geo_cache[key]

    # ۱) لیست داخلی — فقط match دقیق
    if key in KNOWN_PLACES:
        lat, lon, short = KNOWN_PLACES[key]
        _geo_cache[key] = (lat, lon, short)
        return lat, lon, short
    if key in COUNTRY_CENTERS:
        lat, lon, short = COUNTRY_CENTERS[key]
        _geo_cache[key] = (lat, lon, short)
        return lat, lon, short

    headers = {"User-Agent": "ALIMJBot/2.2 (telegram-bot; distance)"}
    try:
        async with httpx.AsyncClient(timeout=15.0, headers=headers, follow_redirects=True) as client:
            # ۲) Open-Meteo Geocoding (دقیق و پایدار)
            try:
                r = await client.get(
                    "https://geocoding-api.open-meteo.com/v1/search",
                    params={"name": place_raw, "count": 5, "language": "fa"},
                )
                if r.status_code == 200:
                    results = (r.json() or {}).get("results") or []
                    if results:
                        # ترجیح ایران/منطقه اگر چند نتیجه
                        best = results[0]
                        for item in results:
                            cc = (item.get("country_code") or "").upper()
                            if cc in ("IR", "IQ", "TR", "AF", "SA", "AE", "SY", "LB"):
                                # اگر کوئری فارسی است اولویت خاورمیانه
                                if any("\u0600" <= ch <= "\u06FF" for ch in place_raw):
                                    best = item
                                    break
                        lat = float(best["latitude"])
                        lon = float(best["longitude"])
                        name = best.get("name") or place_raw
                        country = best.get("country") or ""
                        short = f"{name}، {country}" if country else name
                        _geo_cache[key] = (lat, lon, short)
                        return lat, lon, short
            except Exception as e:
                logger.warning(f"open-meteo geo: {e}")

            # ۳) Nominatim
            queries = [place_raw]
            if not any(x in key for x in ("iran", "ایران", ",")):
                queries.append(f"{place_raw}, Iran")
            for q in queries:
                try:
                    r = await client.get(
                        "https://nominatim.openstreetmap.org/search",
                        params={
                            "q": q,
                            "format": "json",
                            "limit": 5,
                            "accept-language": "fa,en",
                        },
                    )
                    if r.status_code != 200:
                        continue
                    results = r.json() or []
                    if not results:
                        continue

                    def score(item):
                        t = (item.get("type") or "").lower()
                        cls = (item.get("class") or "").lower()
                        imp = float(item.get("importance") or 0)
                        bonus = 0
                        if t in ("city", "town", "municipality", "administrative", "country", "state"):
                            bonus += 3
                        if cls in ("place", "boundary"):
                            bonus += 1
                        dn = (item.get("display_name") or "").lower()
                        if any(x in dn for x in ("village", "hamlet", "روستا", "دهستان", "بخش")):
                            bonus -= 4
                        return imp + bonus

                    results.sort(key=score, reverse=True)
                    best = results[0]
                    lat = float(best["lat"])
                    lon = float(best["lon"])
                    short = _short_name(best.get("display_name") or place_raw, place_raw)
                    _geo_cache[key] = (lat, lon, short)
                    return lat, lon, short
                except Exception:
                    continue

            # ۴) Photon
            try:
                r = await client.get(
                    "https://photon.komoot.io/api/",
                    params={"q": place_raw, "limit": 3},
                )
                if r.status_code == 200:
                    for f in (r.json() or {}).get("features") or []:
                        coords = f.get("geometry", {}).get("coordinates") or []
                        props = f.get("properties") or {}
                        if len(coords) < 2:
                            continue
                        nm = props.get("name") or place_raw
                        country = props.get("country") or ""
                        city = props.get("city") or props.get("state") or nm
                        short = f"{city}، {country}" if country else city
                        _geo_cache[key] = (float(coords[1]), float(coords[0]), short)
                        return _geo_cache[key]
            except Exception:
                pass
    except Exception as e:
        logger.error(f"geocode [{place_raw}]: {e}")
    return None


def haversine(lat1, lon1, lat2, lon2):
    """فاصله خط مستقیم روی کره زمین (کیلومتر) — دقیق"""
    R = 6371.0088  # میانگین شعاع زمین
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(max(0.0, 1 - a)))


def _fmt_duration(hours: float) -> str:
    if hours is None or hours < 0:
        return "—"
    if hours < 0.02:
        return "کمتر از ۱ دقیقه"
    if hours < 1:
        return f"{pn(int(hours * 60))} دقیقه"
    h = int(hours)
    m = int((hours - h) * 60)
    if h >= 24:
        d, h2 = h // 24, h % 24
        return f"{pn(d)} روز و {pn(h2)} ساعت" if h2 else f"{pn(d)} روز"
    return f"{pn(h)} ساعت و {pn(m)} دقیقه" if m else f"{pn(h)} ساعت"


# نام‌های چندکلمه‌ای معروف برای پارس
_MULTIWORD = sorted(
    [k for k in list(KNOWN_PLACES.keys()) + list(COUNTRY_CENTERS.keys()) if " " in k],
    key=len,
    reverse=True,
)


def parse_two_places(text: str):
    """استخراج دو مکان از متن کاربر — دقیق‌تر از قبل"""
    t = (text or "").strip()
    if not t:
        return None

    # جداکننده‌های صریح
    for sep in [
        " تا ", " به ", " -> ", " → ", " — ", " – ",
        " to ", " - ", "\t", "،", ",",
    ]:
        if sep in t:
            a, b = [p.strip() for p in t.split(sep, 1)]
            if a and b:
                return a, b

    # اگر کل متن دو مکان معروف پشت‌سرهم باشد
    low = _norm_place(t)
    # چندکلمه‌ای از ابتدا
    for mw in _MULTIWORD:
        if low.startswith(mw + " "):
            rest = t[len(mw):].strip() if len(t) >= len(mw) else ""
            # try original length match approximately
            rest = low[len(mw):].strip()
            if rest:
                return mw, rest
        if low.endswith(" " + mw):
            first = low[: -len(mw)].strip()
            if first:
                return first, mw

    # دو توکن فارسی/انگلیسی ساده
    parts = t.split()
    if len(parts) == 2:
        return parts[0], parts[1]
    if len(parts) == 3:
        # احتمال: New York London  یا  تهران شهرکرد ؟
        # امتحان 2+1 و 1+2
        return None  # بهتر است کاربر جداکننده بگذارد
    if len(parts) == 4:
        return f"{parts[0]} {parts[1]}", f"{parts[2]} {parts[3]}"
    if len(parts) > 2:
        mid = len(parts) // 2
        return " ".join(parts[:mid]), " ".join(parts[mid:])
    return None


async def _osrm_driving(lat1, lon1, lat2, lon2):
    """فاصله جاده‌ای رایگان با OSRM — ممکن است برای بعضی مسیرها None باشد"""
    try:
        url = f"https://router.project-osrm.org/route/v1/driving/{lon1},{lat1};{lon2},{lat2}"
        async with httpx.AsyncClient(timeout=12.0) as client:
            r = await client.get(url, params={"overview": "false"})
            if r.status_code != 200:
                return None
            js = r.json() or {}
            if js.get("code") != "Ok":
                return None
            routes = js.get("routes") or []
            if not routes:
                return None
            meters = float(routes[0].get("distance") or 0)
            seconds = float(routes[0].get("duration") or 0)
            return meters / 1000.0, seconds / 3600.0
    except Exception as e:
        logger.warning(f"osrm: {e}")
        return None


async def world_distance(place1: str, place2: str = None) -> str:
    if place2 is None:
        parsed = parse_two_places(place1)
        if not parsed:
            return (
                "❌ دو مکان بنویسید.\n\n"
                "مثال‌ها:\n"
                "• تهران تا مشهد\n"
                "• قم کربلا\n"
                "• تهران تا ترکیه\n"
                "• Paris to Tokyo\n"
                "• New York to London"
            )
        place1, place2 = parsed

    place1, place2 = place1.strip(), place2.strip()
    g1, g2 = await asyncio.gather(geocode(place1), geocode(place2))
    if not g1:
        return f"❌ «{place1}» پیدا نشد.\nنام شهر یا کشور را دقیق‌تر بنویسید."
    if not g2:
        return f"❌ «{place2}» پیدا نشد.\nنام شهر یا کشور را دقیق‌تر بنویسید."

    lat1, lon1, n1 = g1
    lat2, lon2, n2 = g2
    km = haversine(lat1, lon1, lat2, lon2)
    miles = km * 0.621371

    if km < 0.05:
        return (
            f"🗺 فاصله جهانی\n\n"
            f"از: {n1}\nتا: {n2}\n\n"
            f"📏 این دو نقطه تقریباً یکی هستند (کمتر از ۵۰ متر)."
        )

    # فاصله جاده‌ای (اختیاری)
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
                    el = ((r.json().get("rows") or [{}])[0].get("elements") or [{}])[0]
                    if el.get("status") == "OK":
                        dist_txt = (el.get("distance") or {}).get("text", "")
                        dur_txt = (el.get("duration") or {}).get("text", "")
                        if dist_txt:
                            driving_info = f"🚗 جاده (گوگل): {dist_txt} — حدود {dur_txt}\n"
        if not driving_info and km < 3000:
            osrm = await _osrm_driving(lat1, lon1, lat2, lon2)
            if osrm:
                d_km, d_hr = osrm
                driving_info = (
                    f"🚗 جاده (تقریبی OSRM): {pn(f'{d_km:,.0f}')} کیلومتر — "
                    f"حدود {_fmt_duration(d_hr)}\n"
                )
    except Exception as e:
        logger.warning(f"driving: {e}")

    return (
        f"🗺 فاصله جهانی\n\n"
        f"📍 از: {n1}\n"
        f"📍 تا: {n2}\n\n"
        f"📏 خط مستقیم (هوایی):\n"
        f"   {pn(f'{km:,.1f}')} کیلومتر\n"
        f"   {pn(f'{miles:,.1f}')} مایل\n\n"
        f"{driving_info}"
        f"⏱ زمان تقریبی با خط مستقیم:\n"
        f"🚗 خودرو (~۸۰km/h): {_fmt_duration(km / 80)}\n"
        f"✈️ هواپیما: {_fmt_duration(km / 800 + 0.5)}\n"
        f"🚶 پیاده: {_fmt_duration(km / 5)}\n\n"
        f"📌 مختصات:\n"
        f"{n1}: {lat1:.4f}, {lon1:.4f}\n"
        f"{n2}: {lat2:.4f}, {lon2:.4f}"
    )

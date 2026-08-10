"""پیش‌بینی هوا ۷ روزه، AQI واقعی، فاصله شهرها — Open-Meteo (بدون کلید، سریع، پایدار)"""
import math
import httpx
from datetime import datetime
from bot.config import config
from bot.logger import logger

_cache = {}
_cache_t = {}

# مختصات کامل شهرهای ایران و عراق + چند شهر مهم
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
    "ساوه": (35.0213, 50.3566), "نجف": (31.9956, 44.3147), "کربلا": (32.6163, 44.0249),
    "کاظمین": (33.3800, 44.3400), "سامرا": (34.1959, 43.8730), "بغداد": (33.3152, 44.3661),
    "کیش": (26.5570, 53.9800), "قشم": (26.9581, 56.2719), "چابهار": (25.2919, 60.6430),
}

WEATHER_CODES = {
    0: "آفتابی ☀️", 1: "عمدتاً صاف 🌤", 2: "نیمه‌ابری ⛅", 3: "ابری ☁️",
    45: "مه 🌫", 48: "مه یخی 🌫", 51: "باران ریز 🌦", 53: "باران متوسط 🌧",
    55: "باران شدید 🌧", 61: "باران 🌧", 63: "باران متوسط 🌧", 65: "باران شدید ⛈",
    71: "برف ❄️", 73: "برف متوسط ❄️", 75: "برف سنگین ❄️", 80: "رگبار 🌦",
    81: "رگبار متوسط 🌧", 82: "رگبار شدید ⛈", 95: "رعدوبرق ⛈", 96: "تگرگ 🌨",
}

AQI_LABELS = [
    (0, 50, "عالی 🟢", "هوا پاک است. مناسب همه فعالیت‌ها."),
    (51, 100, "قابل قبول 🟡", "حساس‌ها کمی مراقب باشند."),
    (101, 150, "ناسالم برای گروه‌های حساس 🟠", "کودکان، سالمندان و بیماران ریوی فعالیت سنگین نکنند."),
    (151, 200, "ناسالم 🔴", "فعالیت در فضای باز را کاهش دهید."),
    (201, 300, "بسیار ناسالم 🟣", "از خروج غیرضروری خودداری کنید."),
    (301, 999, "خطرناک ⚫", "فقط در شرایط اضطراری بیرون بروید."),
]


def pn(n):
    return str(n).translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))


def _norm_city(city: str) -> str:
    c = (city or "").strip().replace("ي", "ی").replace("ك", "ک")
    return c


def _get_coords(city: str):
    c = _norm_city(city)
    if c in CITY_COORDS:
        return CITY_COORDS[c]
    # جستجوی جزئی
    for k, v in CITY_COORDS.items():
        if c in k or k in c:
            return v
    return None





async def weather_forecast(city: str) -> str:
    """پیش‌بینی ۷ روزه — اول Open-Meteo حرفه‌ای، بعد wttr"""
    city = _norm_city(city) or "تهران"
    key = f"fc7_{city}"
    now = datetime.now().timestamp()
    if key in _cache and now - _cache_t.get(key, 0) < getattr(config, "CACHE_TTL", 300):
        return _cache[key]

    coords = _get_coords(city)
    if not coords:
        try:
            async with httpx.AsyncClient(timeout=10.0, headers={"User-Agent": "ALIMJBot/2.0"}) as client:
                r = await client.get(
                    "https://nominatim.openstreetmap.org/search",
                    params={"q": city + ", Iran", "format": "json", "limit": 1},
                )
                if r.status_code == 200 and r.json():
                    item = r.json()[0]
                    coords = (float(item["lat"]), float(item["lon"]))
        except Exception as e:
            logger.error(f"geocode weather {city}: {e}")
    if not coords:
        coords = CITY_COORDS.get("تهران")
    lat, lon = coords

    data = None
    # چند شکل پارامتر + httpx و requests
    param_sets = [
        {
            "latitude": lat, "longitude": lon,
            "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum,windspeed_10m_max,uv_index_max",
            "current": "temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m",
            "timezone": "Asia/Tehran", "forecast_days": 7,
        },
        {
            "latitude": lat, "longitude": lon,
            "daily": "weathercode,temperature_2m_max,temperature_2m_min,precipitation_sum,windspeed_10m_max,uv_index_max",
            "current_weather": "true",
            "timezone": "Asia/Tehran", "forecast_days": 7,
        },
    ]
    for params in param_sets:
        try:
            async with httpx.AsyncClient(timeout=15.0, headers={"User-Agent": "Mozilla/5.0"}) as client:
                r = await client.get("https://api.open-meteo.com/v1/forecast", params=params)
                if r.status_code == 200:
                    data = r.json()
                    break
        except Exception as e:
            logger.error(f"open-meteo httpx: {e}")
        try:
            import requests as _req
            r = _req.get("https://api.open-meteo.com/v1/forecast", params=params, timeout=15,
                         headers={"User-Agent": "Mozilla/5.0"})
            if r.status_code == 200:
                data = r.json()
                break
        except Exception as e:
            logger.error(f"open-meteo requests: {e}")

    if data:
        # پشتیبانی هر دو فرمت current / current_weather
        current = data.get("current") or {}
        cw = data.get("current_weather") or {}
        daily = data.get("daily") or {}
        times = daily.get("time") or []
        tmax = daily.get("temperature_2m_max") or []
        tmin = daily.get("temperature_2m_min") or []
        codes = daily.get("weather_code") or daily.get("weathercode") or []
        precip = daily.get("precipitation_sum") or []
        wind = daily.get("windspeed_10m_max") or daily.get("wind_speed_10m_max") or []
        uv = daily.get("uv_index_max") or []

        if current:
            cur_temp = current.get("temperature_2m", "?")
            cur_hum = current.get("relative_humidity_2m", "?")
            cur_code = current.get("weather_code") or current.get("weathercode") or 0
            cur_wind = current.get("wind_speed_10m", "?")
        else:
            cur_temp = cw.get("temperature", "?")
            cur_hum = "?"
            cur_code = cw.get("weathercode") or cw.get("weather_code") or 0
            cur_wind = cw.get("windspeed", cw.get("wind_speed", "?"))
        try:
            cur_code = int(cur_code)
        except Exception:
            cur_code = 0
        cur_desc = WEATHER_CODES.get(cur_code, "نامشخص")

        lines = [
            f"🌤 پیش‌بینی هوای {city} (۷ روزه)",
            "",
            f"📍 الان: {pn(cur_temp)}°C  {cur_desc}",
            f"💧 رطوبت: {pn(cur_hum)}%  |  💨 باد: {pn(cur_wind)} km/h",
            "━━━━━━━━━━━━━━━━━━━━",
        ]
        day_names = ["امروز", "فردا", "پس‌فردا", "روز ۴", "روز ۵", "روز ۶", "روز ۷"]
        for i in range(min(7, len(times))):
            d = times[i][5:] if times[i] else ""
            mx = tmax[i] if i < len(tmax) else "?"
            mn = tmin[i] if i < len(tmin) else "?"
            try:
                code = int(codes[i]) if i < len(codes) else 0
            except Exception:
                code = 0
            desc = WEATHER_CODES.get(code, "")
            pr = precip[i] if i < len(precip) else 0
            wd = wind[i] if i < len(wind) else "?"
            u = uv[i] if i < len(uv) else "?"
            rain = f"  |  🌧 {pn(pr)}mm" if pr not in (None, 0, "0", 0.0) and str(pr) not in ("0", "0.0") else ""
            lines.append(f"• {day_names[i]} ({d})")
            lines.append(f"  {pn(mn)}° ~ {pn(mx)}°  {desc}")
            lines.append(f"  💨 {pn(wd)} km/h  |  ☀️ UV {pn(u)}{rain}")

        result = "\n".join(lines)
        _cache[key] = result
        _cache_t[key] = now
        return result

    # ——— fallback wttr (حداکثر ۳ روز دارد) + ترجمه ———
    EN2FA = {
        "Sunny": "آفتابی ☀️", "Clear": "صاف ☀️", "Partly cloudy": "نیمه‌ابری ⛅",
        "Cloudy": "ابری ☁️", "Overcast": "ابری کامل ☁️", "Mist": "مه 🌫",
        "Patchy rain possible": "احتمال باران 🌦", "Rain": "بارانی 🌧",
        "Thundery outbreaks possible": "رعدوبرق ⛈", "Snow": "برفی ❄️",
    }
    try:
        async with httpx.AsyncClient(timeout=12.0, headers={"User-Agent": "Mozilla/5.0"}) as client:
            r = await client.get(f"https://wttr.in/{city}?format=j1&lang=fa")
            if r.status_code != 200:
                r = await client.get(f"https://wttr.in/{city}?format=j1")
            if r.status_code == 200:
                j = r.json()
                cur = j["current_condition"][0]
                days = j.get("weather", [])[:7]
                desc0 = cur.get("lang_fa", [{}])
                if isinstance(desc0, list) and desc0:
                    cur_desc = desc0[0].get("value") or cur.get("weatherDesc", [{}])[0].get("value", "")
                else:
                    cur_desc = cur.get("weatherDesc", [{}])[0].get("value", "")
                cur_desc = EN2FA.get(cur_desc, cur_desc)
                lines = [
                    f"🌤 پیش‌بینی هوای {city}",
                    "",
                    f"📍 الان: {pn(cur.get('temp_C','?'))}°C — {cur_desc}",
                    f"💧 رطوبت: {pn(cur.get('humidity','?'))}%",
                    "━━━━━━━━━━━━━━━━━━━━",
                ]
                names = ["امروز", "فردا", "پس‌فردا", "روز ۴", "روز ۵", "روز ۶", "روز ۷"]
                for i, d in enumerate(days):
                    mx, mn = d.get("maxtempC", "?"), d.get("mintempC", "?")
                    desc = ""
                    try:
                        if d.get("hourly") and d["hourly"][0].get("lang_fa"):
                            desc = d["hourly"][4 if len(d["hourly"])>4 else 0]["lang_fa"][0]["value"]
                        else:
                            desc = d["hourly"][4 if len(d["hourly"])>4 else 0]["weatherDesc"][0]["value"]
                    except Exception:
                        pass
                    desc = EN2FA.get(desc, desc)
                    lines.append(f"• {names[i]}: {pn(mn)}° ~ {pn(mx)}°  {desc}")
                result = "\n".join(lines)
                _cache[key] = result
                _cache_t[key] = now
                return result
    except Exception as e:
        logger.error(f"wttr fallback {city}: {e}")

    return (
        f"❌ پیش‌بینی هوای {city} موقتاً در دسترس نیست.\n"
        "لطفاً چند لحظه بعد دوباره امتحان کنید."
    )



async def air_quality(city: str) -> str:
    """شاخص کیفیت هوا واقعی با Open-Meteo Air Quality API"""
    key = f"aqi_{city}"
    now = datetime.now().timestamp()
    if key in _cache and now - _cache_t.get(key, 0) < config.CACHE_TTL:
        return _cache[key]

    lat, lon = _get_coords(city)
    try:
        url = "https://air-quality-api.open-meteo.com/v1/air-quality"
        params = {
            "latitude": lat,
            "longitude": lon,
            "current": "european_aqi,pm10,pm2_5,carbon_monoxide,nitrogen_dioxide,ozone,sulphur_dioxide,dust",
            "timezone": "Asia/Tehran",
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(url, params=params)
            r.raise_for_status()
            data = r.json()

        cur = data.get("current", {})
        aqi = cur.get("european_aqi")
        pm25 = cur.get("pm2_5")
        pm10 = cur.get("pm10")
        no2 = cur.get("nitrogen_dioxide")
        o3 = cur.get("ozone")
        so2 = cur.get("sulphur_dioxide")
        co = cur.get("carbon_monoxide")
        dust = cur.get("dust")

        label, advice = "نامشخص", ""
        if aqi is not None:
            for low, high, lab, adv in AQI_LABELS:
                if low <= aqi <= high:
                    label, advice = lab, adv
                    break

        lines = [
            f"🌫 **کیفیت هوا — {city}** (زمان واقعی)\n",
            f"📊 **شاخص AQI (اروپایی):** {pn(aqi) if aqi is not None else '—'}  →  **{label}**\n",
            f"💡 {advice}\n" if advice else "",
            "━━━━━━━━━━━━━━━━━━━━",
            f"• PM2.5: {pn(pm25) if pm25 is not None else '—'} µg/m³",
            f"• PM10: {pn(pm10) if pm10 is not None else '—'} µg/m³",
            f"• NO₂: {pn(no2) if no2 is not None else '—'} µg/m³",
            f"• O₃: {pn(o3) if o3 is not None else '—'} µg/m³",
            f"• SO₂: {pn(so2) if so2 is not None else '—'} µg/m³",
            f"• CO: {pn(co) if co is not None else '—'} µg/m³",
        ]
        if dust is not None:
            lines.append(f"• گردوغبار: {pn(dust)} µg/m³")

        result = "\n".join(lines)
        _cache[key] = result
        _cache_t[key] = now
        return result
    except Exception as e:
        logger.error(f"aqi {city}: {e}")
        return f"❌ کیفیت هوای {city} موقتاً در دسترس نیست."


def city_distance(city1: str, city2: str) -> str:
    """فاصله دقیق بین دو شهر با فرمول Haversine"""
    c1 = CITY_COORDS.get(city1.strip())
    c2 = CITY_COORDS.get(city2.strip())
    if not c1 or not c2:
        available = "، ".join(list(CITY_COORDS.keys())[:15]) + " و ..."
        return (
            f"❌ یکی از شهرها پیدا نشد.\n\n"
            f"شهرهای پشتیبانی‌شده:\n{available}\n\n"
            f"مثال: `تهران مشهد`"
        )
    R = 6371.0
    lat1, lon1 = math.radians(c1[0]), math.radians(c1[1])
    lat2, lon2 = math.radians(c2[0]), math.radians(c2[1])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    dist = 2 * R * math.asin(math.sqrt(a))
    hours = dist / 80
    h = int(hours)
    m = int((hours - h) * 60)
    return (
        f"🗺 **فاصله بین شهرها**\n\n"
        f"📍 {city1}  ↔  {city2}\n\n"
        f"📏 فاصله هوایی: **{pn(f'{dist:.0f}')} کیلومتر**\n"
        f"🚗 تقریبی با خودرو: حدود **{pn(h)} ساعت و {pn(m)} دقیقه**"
    )

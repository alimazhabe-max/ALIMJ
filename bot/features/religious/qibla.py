"""قبله‌نما — محاسبه جهت قبله از مختصات شهر"""
import math
from bot.api.weather_extra import CITY_COORDS  # reuse

KAABA = (21.4225, 39.8262)


def qibla_direction(city: str) -> str:
    coords = CITY_COORDS.get(city)
    if not coords:
        return f"❌ شهر «{city}» پیدا نشد. ابتدا شهر را تنظیم کنید."

    lat1, lon1 = math.radians(coords[0]), math.radians(coords[1])
    lat2, lon2 = math.radians(KAABA[0]), math.radians(KAABA[1])

    dlon = lon2 - lon1
    x = math.sin(dlon) * math.cos(lat2)
    y = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
    bearing = math.degrees(math.atan2(x, y))
    bearing = (bearing + 360) % 360

    directions = [
        (0, "شمال"), (45, "شمال‌شرقی"), (90, "شرق"), (135, "جنوب‌شرقی"),
        (180, "جنوب"), (225, "جنوب‌غربی"), (270, "غرب"), (315, "شمال‌غربی"), (360, "شمال")
    ]
    closest = min(directions, key=lambda d: abs(d[0] - bearing))
    dir_name = closest[1]

    return (
        f"🕋 **قبله‌نما — {city}**\n\n"
        f"📐 زاویه: **{bearing:.1f}°**\n"
        f"🧭 جهت تقریبی: **{dir_name}**\n\n"
        f"از موقعیت فعلی رو به {dir_name} بایستید تا رو به قبله باشید."
    )

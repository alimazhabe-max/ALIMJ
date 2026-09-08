"""اذکار روزانه"""
import random
from datetime import datetime
import pytz
from bot.config import config

tehran_tz = pytz.timezone(config.TIMEZONE)

ADHKAR = [
    "سبحان الله و بحمده، سبحان الله العظیم",
    "لا اله الا الله وحده لا شریک له، له الملک و له الحمد و هو علی کل شیء قدیر",
    "استغفر الله ربی و اتوب الیه",
    "اللهم صل علی محمد و آل محمد",
    "حسبی الله لا اله الا هو علیه توکلت و هو رب العرش العظیم",
    "لا حول و لا قوة الا بالله العلی العظیم",
    "رب اغفر لی و لوالدی و للمؤمنین",
    "اللهم انی اسالک العفو و العافیة",
    "یا حی یا قیوم برحمتک استغیث",
    "اللهم بارک لنا فی رجب و شعبان و بلغنا رمضان",
    "سبحان الله و الحمد لله و لا اله الا الله و الله اکبر",
    "اللهم صل علی فاطمة و ابیها و بعلها و بنیها",
]


def daily_adhkar(user_id: int = 0) -> str:
    day = datetime.now(tehran_tz).strftime("%Y%m%d")
    random.seed(f"{user_id}{day}adhkar")
    selected = random.sample(ADHKAR, min(5, len(ADHKAR)))
    random.seed()
    lines = ["📿 **اذکار امروز**\n"]
    for i, z in enumerate(selected, 1):
        lines.append(f"{i}. {z}")
    lines.append("\n💚 با حضور قلب بخوانید.")
    return "\n".join(lines)

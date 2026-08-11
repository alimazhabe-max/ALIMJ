"""سرگرمی — فال حافظ، جوک، دانستنی، چالش"""
import random
import httpx
from bot.logger import logger

def pn(n):
    return str(n).translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))


# ——— فال حافظ (API + fallback) ———
HAFEZ_LOCAL = [
    ("الا یا ایها الساقی ادر کاسا و ناولها", "که عشق آسان نمود اول ولی افتاد مشکل‌ها", "صبر و توکل؛ گره‌ها به تدریج باز می‌شود."),
    ("اگر آن ترک شیرازی به دست آرد دل ما را", "به خال هندویش بخشم سمرقند و بخارا را", "عشق و دلدادگی در راه است؛ سخاوتمند باش."),
    ("دوش وقت سحر از غصه نجاتم دادند", "واندر آن ظلمت شب آب حیاتم دادند", "گشایش نزدیک است؛ ناامید نشو."),
    ("یوسف گم‌گشته بازآید به کنعان غم مخور", "کلبه احزان شود روزی گلستان غم مخور", "صبر کن؛ خیر در راه است."),
    ("هر آنکه جانب اهل خدا نگه دارد", "خداش در همه حال از بلا نگه دارد", "پایبندی به خوبی‌ها محافظ توست."),
    ("با مدعی مگویید اسرار عشق و مستی", "تا بی‌خبر بمیرد در درد خودپرستی", "اسرار دل را نگه دار."),
    ("در این بازار اگر سودی است با درویش خرسند است", "خدایا منعمم گردان به درویشی و خرسندی", "قناعت آرامش می‌آورد."),
    ("زاهد ظاهرپرست از حال ما آگاه نیست", "در حق ما هرچه گوید جای هیچ اکراه نیست", "به حرف دیگران وابسته نباش."),
]


async def hafez_fal(user_id: int = 0) -> str:
    """فال حافظ — تلاش از API عمومی + fallback"""
    try:
        async with httpx.AsyncClient(timeout=8.0) as c:
            # API عمومی حافظ
            r = await c.get("https://api.ganjoor.net/api/ganjoor/hafez/faal")
            if r.status_code == 200:
                data = r.json()
                title = data.get("title") or data.get("poem", {}).get("title") or "غزل حافظ"
                verses = data.get("verses") or data.get("poem", {}).get("verses") or []
                meaning = data.get("interpretation") or data.get("plainText") or ""
                body = "\n".join(
                    (v.get("text") if isinstance(v, dict) else str(v)) for v in verses[:8]
                ) if verses else data.get("plainText", "")
                if body:
                    return (
                        f"📖 **فال حافظ**\n\n"
                        f"*{title}*\n\n"
                        f"{body}\n\n"
                        + (f"💡 {meaning[:300]}\n\n" if meaning else "")
                        + "🔮 نیت کنید و تأمل نمایید."
                    )
    except Exception as e:
        logger.error(f"hafez api: {e}")

    couplet, next_c, advice = random.choice(HAFEZ_LOCAL)
    return (
        f"📖 **فال حافظ**\n\n"
        f"{couplet}\n"
        f"{next_c}\n\n"
        f"💡 {advice}\n\n"
        f"🔮 نیت کنید و تأمل نمایید."
    )


# ——— جوک‌ها از farsijokes.com (۵۵۱۶ جوک دسته‌بندی‌شده) ———
import json
from pathlib import Path

_JOKES_CACHE = None


def _load_jokes():
    global _JOKES_CACHE
    if _JOKES_CACHE is not None:
        return _JOKES_CACHE
    path = Path(__file__).parent / "jokes_data.json"
    try:
        with open(path, encoding="utf-8") as f:
            _JOKES_CACHE = json.load(f)
    except Exception:
        _JOKES_CACHE = {
            "labels": {"general": "😄 عمومی"},
            "jokes": {"general": ["جوکی موجود نیست."]},
        }
    return _JOKES_CACHE


def get_joke_categories() -> dict:
    """برگرداندن {key: label} دسته‌ها"""
    data = _load_jokes()
    return data.get("labels", {})


def random_joke(category: str = None) -> str:
    """جوک تصادفی از یک دسته یا از همه"""
    data = _load_jokes()
    jokes_map = data.get("jokes", {})
    labels = data.get("labels", {})
    if category and category in jokes_map and jokes_map[category]:
        text = random.choice(jokes_map[category])
        label = labels.get(category, category)
    else:
        # از همه دسته‌ها
        all_jokes = []
        for lst in jokes_map.values():
            all_jokes.extend(lst)
        if not all_jokes:
            return "جوکی موجود نیست."
        text = random.choice(all_jokes)
        label = "تصادفی"
    return f"😂 **جوک ({label})**\n\n{text}"


# سازگاری با کد قبلی
JOKES = []  # دیگر استفاده نمی‌شود؛ از random_joke استفاده کنید

FACTS = [
    "عسل تنها غذایی است که هرگز فاسد نمی‌شود.",
    "قلب کوسه در سرش نیست؛ نزدیک آبشش است.",
    "اثر انگشت گوریل و انسان متفاوت است اما هر دو یکتاست.",
    "طول رگ‌های بدن انسان حدود ۱۰۰ هزار کیلومتر است.",
    "اختاپوس سه قلب دارد.",
    "بیشتر گرد و غبار خانه از پوست مرده انسان است.",
    "نهنگ آبی بزرگ‌ترین حیوان تاریخ زمین است.",
    "مغز انسان حدود ۲۰ وات انرژی مصرف می‌کند.",
    "در فضا اشک جاری نمی‌شود؛ به شکل حباب می‌ماند.",
    "زبان قوی‌ترین عضله نسبت به اندازه‌اش در بدن است.",
    "زرافه فقط حدود ۳۰ دقیقه در شبانه‌روز می‌خوابد.",
    "نور خورشید حدود ۸ دقیقه طول می‌کشد تا به زمین برسد.",
    "کوه اورست هر سال چند میلی‌متر رشد می‌کند.",
    "انسان تنها حیوانی است که می‌تواند آگاهانه نفس را حبس کند.",
    "خواب دیدن معمولاً در مرحله REM رخ می‌دهد.",
    "اسکلت انسان در بدو تولد حدود ۲۷۰ استخوان دارد و بعد کمتر می‌شود.",
    "بادام‌زمینی جزو آجیل‌ها نیست؛ جزو حبوبات است.",
    "چشم‌های شترمرغ از مغزش بزرگ‌ترند.",
    "در هر ثانیه خورشید میلیون‌ها تن ماده را به انرژی تبدیل می‌کند.",
    "اثر انگشت حتی در دوقلوهای همسان متفاوت است.",
]

CHALLENGES = [
    "امروز به یک نفر بدون مناسبت پیام محبت‌آمیز بده.",
    "۳۰ دقیقه بدون گوشی بمان و فقط نفس عمیق بکش.",
    "یک کار عقب‌افتاده را همین امروز تمام کن.",
    "به کسی که فراموش کردی پیام بده و احوالش را بپرس.",
    "۱۰ چیز که بابت آن‌ها شکرگزاری می‌کنی را بنویس.",
    "امروز یک عادت بد را آگاهانه متوقف کن.",
    "۱۵ دقیقه پیاده‌روی بدون هدف مشخص.",
    "به جای شکایت، یک راه‌حل پیشنهاد بده.",
    "یک صفحه کتاب بخوان — هر کتابی.",
    "قبل از خواب گوشی را یک ساعت کنار بگذار.",
    "به خودت بگو: من کافی هستم — و باور کن.",
    "یک کار خیر کوچک بدون اینکه کسی بفهمد انجام بده.",
]


async def joke_of_day(category: str = None) -> str:
    return random_joke(category)


async def fact_of_day() -> str:
    return f"🧠 **دانستنی**\n\n{random.choice(FACTS)}"


async def daily_challenge() -> str:
    return (
        f"💪 **چالش امروز**\n\n"
        f"{random.choice(CHALLENGES)}\n\n"
        f"✅ وقتی انجام دادی به خودت امتیاز بده!"
    )

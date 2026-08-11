"""سرگرمی — فال حافظ، جوک، دانستنی، چالش"""
import random
import httpx
from bot.logger import logger

def pn(n):
    return str(n).translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))


# ——— فال حافظ (شبیه hafez.taktemp.com) ———
HAFEZ_OPENING = (
    "ای حافظ شیرازی! تو محرم هر رازی!\n"
    "تو را به خدا و به شاخ نباتت قسم می‌دهم "
    "که هر چه صلاح و مصلحت می‌بینی برایم آشکار و آرزوی مرا برآورده سازی."
)

HAFEZ_LOCAL = [
    (
        "غزل شمارهٔ ۱",
        "الا یا ایها الساقی ادر کأساً و ناولها\nکه عشق آسان نمود اول ولی افتاد مشکل‌ها\n"
        "به بوی نافه‌ای کآخر صبا زان طره بگشاید\nز تاب جعد مشکینش چه خون افتاد در دل‌ها",
        "صبر و توکل؛ عشق در آغاز آسان می‌نماید اما راهش پر از آزمون است. با ایمان پیش برو.",
    ),
    (
        "غزل شمارهٔ ۳",
        "اگر آن ترک شیرازی به دست آرد دل ما را\nبه خال هندویش بخشم سمرقند و بخارا را\n"
        "بده ساقی می باقی که در جنت نخواهی یافت\nکنار آب رکن‌آباد و گلگشت مصلا را",
        "عشق و دلدادگی در راه است. سخاوت و بخشش نیتت را به خیر می‌رساند.",
    ),
    (
        "غزل شمارهٔ ۲۲",
        "دوش وقت سحر از غصه نجاتم دادند\nواندر آن ظلمت شب آب حیاتم دادند\n"
        "بی‌خود از شعشعه پرتو ذاتم کردند\nباده از جام تجلی صفاتم دادند",
        "گشایش نزدیک است. از تاریکی عبور می‌کنی و نور به تو می‌رسد؛ ناامید نشو.",
    ),
    (
        "غزل شمارهٔ ۲۵۷",
        "یوسف گم‌گشته باز آید به کنعان غم مخور\nکلبهٔ احزان شود روزی گلستان غم مخور\n"
        "ای دل غمدیده حالت به شود دلبد مکن\nوین سر شوریده باز آید به سامان غم مخور",
        "صبر کن؛ آنچه از دست رفته بازمی‌گردد و غم جای خود را به شادی می‌دهد.",
    ),
]


def _format_verses(verses: list) -> str:
    """چیدمان ابیات مثل سایت‌های فال حافظ (مصراع‌ها جفت‌جفت)"""
    lines = []
    couplet = []
    for v in verses:
        if not isinstance(v, dict):
            continue
        text = (v.get("text") or "").strip()
        if not text:
            continue
        couplet.append(text)
        # versePosition 0 = مصراع اول، 1 = مصراع دوم
        pos = v.get("versePosition")
        if pos == 1 or len(couplet) >= 2:
            lines.append("\n".join(couplet))
            couplet = []
    if couplet:
        lines.append("\n".join(couplet))
    return "\n\n".join(lines)


async def hafez_fal(user_id: int = 0) -> str:
    """
    فال حافظ — شبیه hafez.taktemp.com
    نیت → دعا → غزل کامل → تفسیر
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as c:
            r = await c.get("https://api.ganjoor.net/api/ganjoor/hafez/faal")
            if r.status_code == 200:
                data = r.json() or {}
                title = data.get("title") or "غزل حافظ"
                full_title = data.get("fullTitle") or title
                verses = data.get("verses") or []
                body = _format_verses(verses) if verses else (data.get("plainText") or "").replace("\r\n", "\n\n")
                # تفسیر: خلاصه هوش‌مصنوعی گنجور
                meaning = (data.get("poemSummary") or "").strip()
                if not meaning:
                    # از coupletSummary اولین بیت
                    for v in verses:
                        if isinstance(v, dict) and v.get("coupletSummary"):
                            meaning = v["coupletSummary"]
                            break
                if meaning.startswith("هوش مصنوعی:"):
                    meaning = meaning.replace("هوش مصنوعی:", "", 1).strip()

                if body:
                    parts = [
                        "🔮 **فال حافظ**",
                        "",
                        "نیت کنید…",
                        "",
                        f"📿 {HAFEZ_OPENING}",
                        "",
                        "━━━━━━━━━━━━━━━━━━━━",
                        f"📖 **{title}**",
                        f"_{full_title}_" if full_title != title else "",
                        "",
                        body.strip(),
                        "",
                    ]
                    if meaning:
                        parts.extend([
                            "━━━━━━━━━━━━━━━━━━━━",
                            "💡 **تفسیر فال**",
                            "",
                            meaning[:900],
                            "",
                        ])
                    parts.append("🕯️ برای شادی روح حافظ، صلوات یا فاتحه‌ای نثار کنید.")
                    return "\n".join(p for p in parts if p is not None)
    except Exception as e:
        logger.error(f"hafez api: {e}")

    title, body, advice = random.choice(HAFEZ_LOCAL)
    return (
        f"🔮 **فال حافظ**\n\n"
        f"نیت کنید…\n\n"
        f"📿 {HAFEZ_OPENING}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📖 **{title}**\n\n"
        f"{body}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"💡 **تفسیر فال**\n\n"
        f"{advice}\n\n"
        f"🕯️ برای شادی روح حافظ، صلوات یا فاتحه‌ای نثار کنید."
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


def random_joke(category: str = None, user_id: int = None) -> str:
    """جوک تصادفی — برای هر کاربر تکراری نمی‌فرستد"""
    import hashlib
    data = _load_jokes()
    jokes_map = data.get("jokes", {})
    labels = data.get("labels", {})

    if category and category in jokes_map and jokes_map[category]:
        pool = list(jokes_map[category])
        label = labels.get(category, category)
    else:
        pool = []
        for lst in jokes_map.values():
            pool.extend(lst)
        label = "تصادفی"

    if not pool:
        return "جوکی موجود نیست."

    # حذف جوک‌هایی که این کاربر قبلاً دیده
    if user_id:
        try:
            from bot.database import get_sent_joke_hashes, mark_joke_sent, reset_sent_jokes
            seen = get_sent_joke_hashes(user_id)
            fresh = [j for j in pool if hashlib.md5(j.encode("utf-8")).hexdigest() not in seen]
            if not fresh:
                # همه را دیده — از نو شروع کن
                reset_sent_jokes(user_id)
                fresh = pool
            text = random.choice(fresh)
            mark_joke_sent(user_id, hashlib.md5(text.encode("utf-8")).hexdigest())
        except Exception:
            text = random.choice(pool)
    else:
        text = random.choice(pool)

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


async def joke_of_day(category: str = None, user_id: int = None) -> str:
    return random_joke(category, user_id=user_id)


async def fact_of_day() -> str:
    return f"🧠 **دانستنی**\n\n{random.choice(FACTS)}"


async def daily_challenge() -> str:
    return (
        f"💪 **چالش امروز**\n\n"
        f"{random.choice(CHALLENGES)}\n\n"
        f"✅ وقتی انجام دادی به خودت امتیاز بده!"
    )

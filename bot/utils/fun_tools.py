"""
سرگرمی — فال حافظ، استخاره واقعی از آوینی، حقیقت/جرات، جوک، دانستنی، چالش
"""
import random
import hashlib
import re
import httpx
from datetime import datetime
import pytz
from bot.config import config
from bot.logger import logger

tehran_tz = pytz.timezone(config.TIMEZONE)

HAFEZ = [
    "اگر آن ترک شیرازی به دست آرد دل ما را / به خال هندویش بخشم سمرقند و بخارا را",
    "صلاح کار کجا و من خراب کجا / ببین تفاوت ره کز کجاست تا به کجا",
    "در این زمانه رفیقی که خالی از خلل است / صراحی می ناب و سفینه غزل است",
    "یوسف گمگشته بازآید به کنعان غم مخور / کلبه احزان شود روزی گلستان غم مخور",
    "با زمانه بساز یا مساز که دوران / نسازد با کسی که با زمانه نسازد",
    "آسایش دو گیتی تفسیر این دو حرف است / با دوستان مروت با دشمنان مدارا",
    "سحر با باد می‌گفتم حدیث آرزومندی / خطاب آمد که واثق شو به الطاف خداوندی",
    "هر آن که جانب اهل وفا نگه دارد / خداش در همه حال از بلا نگه دارد",
    "با مدعی مگویید اسرار عشق و مستی / تا بی‌خبر بمیرد در درد خودپرستی",
    "هزار نکته باریکتر ز مو اینجاست / نه هر که سر بتراشد قلندری داند",
    "دوش دیدم که ملائک در میخانه زدند / گل آدم بسرشتند و به پیمانه زدند",
    "ما را به رندی افسانه کردند / پیران جاهل این افسانه کردند",
]

# fallback محلی اگر سایت در دسترس نبود
ISTIKHARA_FALLBACK = [
    ("خوب ✅", "این کار به صلاح شماست. با توکل پیش بروید. ان‌شاءالله نتیجه مطلوب حاصل می‌شود."),
    ("متوسط 🟡", "مصلحت در احتیاط است. عجله نکنید و بیشتر فکر کنید."),
    ("بد ❌", "بهتر است از این کار صرف‌نظر کنید. خیر شما در ترک آن است."),
    ("خوب با تأخیر 🟢", "نتیجه خوب است اما زمان بیشتری نیاز دارد. صبور باشید."),
    ("نیاز به مشورت 🔵", "با افراد آگاه و معتمد مشورت کنید سپس تصمیم بگیرید."),
    ("بسیار خوب ✅✅", "بسیار خوب است. با توکل به خدا اقدام کنید. ان‌شاءالله به همه اهداف‌تان می‌رسید."),
    ("ترک کنید ❌", "ترک این کار به مصلحت نزدیک‌تر است."),
]

TRUTH = [
    "آخرین باری که دروغ گفتی کی بود؟",
    "بزرگ‌ترین ترس تو چیست؟",
    "اگر یک آرزو داشتی چه می‌خواستی؟",
    "خجالت‌آورترین خاطره مدرسه‌ات چیست؟",
    "به چه کسی بیشتر از همه اعتماد داری؟",
    "اگر می‌توانستی یک چیز را در گذشته عوض کنی، چه بود؟",
    "آخرین پیام ناخوانده‌ات از کیست؟",
    "بیشترین پولی که تا حالا خرج کردی برای چه بود؟",
]

DARE = [
    "یک پیام صوتی با لهجه عجیب بفرست!",
    "اسمت را برعکس بنویس و بفرست.",
    "یک ایموجی بفرست که حالت الان را نشان دهد.",
    "یک جمله با فقط ۵ کلمه بساز که خنده‌دار باشد.",
    "بگو امروز چه رنگی پوشیده‌ای.",
    "یک تعریف از خودت بکن (بدون خجالت!).",
    "یک آرزوی عجیب و غریب بنویس.",
]

JOKES = [
    "معلم: چرا دیر آمدی؟ دانش‌آموز: چون یک تابلو نوشته بود مدرسه این طرف، منم اومدم این طرف!",
    "یکی رفت دکتر گفت آقا من یادم می‌ره. دکتر گفت از کی؟ گفت کی چی؟",
    "پسره به پدرش گفت بابا می‌تونم برم پارک؟ پدر گفت برو ولی مواظب باش گم نشی. پسره رفت و برگشت گفت بابا گم شدم!",
    "چرا کامپیوتر به دکتر رفت؟ چون ویروس گرفته بود!",
    "مرده به زنش گفت طلاقت می‌دم. زن گفت چرا؟ مرد گفت چون دوستت دارم. زن گفت خب بمون دیگه! مرد گفت نه، دوست دارم طلاقت بدم.",
    "یک نفر زنگ زد پلیس گفت دزدم اومده خونه. پلیس گفت داره چیکار می‌کنه؟ گفت داره با من حرف می‌زنه!",
]

FACTS = [
    "قلب انسان در طول عمر حدود ۲.۵ میلیارد بار می‌تپد.",
    "عسل تنها ماده غذایی است که فاسد نمی‌شود.",
    "اختاپوس سه قلب دارد.",
    "نور خورشید ۸ دقیقه و ۲۰ ثانیه طول می‌کشد تا به زمین برسد.",
    "مغز انسان حدود ۷۵٪ آب است.",
    "در فضا خون انسان هم جوش می‌آید هم یخ می‌زند.",
    "زرافه خواب را ایستاده می‌بیند و فقط حدود ۳۰ دقیقه در روز می‌خوابد.",
    "اثر انگشت هر انسان منحصربه‌فرد است — حتی دوقلوها.",
    "ماهی قرمز حافظه‌اش بیشتر از ۳ ثانیه است (حدود چند ماه!).",
    "کوه اورست هر سال چند میلی‌متر بلندتر می‌شود.",
]

CHALLENGES = [
    "امروز به یک نفر بدون دلیل محبت کن یا تشکر کن.",
    "۱۵ دقیقه پیاده‌روی بدون موبایل.",
    "یک صفحه از یک کتاب بخوان.",
    "امروز هیچ شکایتی نکن — فقط مثبت باش.",
    "یک لیوان آب اضافه بنوش.",
    "۵ چیز که بابت‌شان شکرگزاری می‌کنی را بنویس.",
    "یک کار عقب‌افتاده را امروز تمام کن.",
    "به مدت ۱۰ دقیقه فقط نفس عمیق بکش و سکوت کن.",
    "به یک دوست قدیمی پیام بده.",
    "امروز زودتر بخواب (حداقل ۳۰ دقیقه).",
]


def pn(n):
    return str(n).translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))


def hafez_fal(user_id: int = 0) -> str:
    day = datetime.now(tehran_tz).strftime("%Y%m%d")
    seed = int(hashlib.md5(f"{user_id}{day}hafez".encode()).hexdigest(), 16)
    random.seed(seed)
    verse = random.choice(HAFEZ)
    random.seed()
    return f"📖 **فال حافظ**\n\n«{verse}»\n\n🔮 نیت کنید و تأمل نمایید."


async def istikhara(user_id: int = 0) -> str:
    """استخاره از سایت آوینی (old.aviny.com) با fallback محلی"""
    # انتخاب صفحه تصادفی ۱ تا حدود ۶۰۰ (سایت حدود همین تعداد دارد)
    day = datetime.now(tehran_tz).strftime("%Y%m%d%H")
    seed = int(hashlib.md5(f"{user_id}{day}ist".encode()).hexdigest(), 16)
    page = (seed % 580) + 1  # ۱ تا ۵۸۰

    try:
        url = f"https://old.aviny.com/quran/estekhareh/index2.aspx?page={page}"
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }) as client:
            r = await client.get(url)
            r.raise_for_status()
            text = r.text

        # استخراج نتیجه کلی
        # الگوهای رایج در صفحه
        result_general = ""
        result_marriage = ""
        result_trade = ""
        good_bad = ""
        chapter = ""
        ayeh = ""

        # جستجوی متن‌های کلیدی
        m = re.search(r'نتیجه\s*کلی[:\s]*(.+?)(?:</|نتیجه|$)', text, re.DOTALL | re.IGNORECASE)
        if m:
            result_general = re.sub(r'<[^>]+>', '', m.group(1)).strip()[:300]

        m = re.search(r'ازدواج[:\s]*(.+?)(?:</|تجارت|$)', text, re.DOTALL | re.IGNORECASE)
        if m:
            result_marriage = re.sub(r'<[^>]+>', '', m.group(1)).strip()[:200]

        m = re.search(r'تجارت[:\s]*(.+?)(?:</|سوره|$)', text, re.DOTALL | re.IGNORECASE)
        if m:
            result_trade = re.sub(r'<[^>]+>', '', m.group(1)).strip()[:200]

        # پیدا کردن خوب/بد
        if any(w in text for w in ["حتما انجام بده", "بسیار خوب", "خوب است"]):
            good_bad = "خوب ✅"
        elif any(w in text for w in ["هرگز انجام نده", "بد است", "ترک کن"]):
            good_bad = "بد ❌"
        elif "متوسط" in text or "احتیاط" in text:
            good_bad = "متوسط 🟡"
        else:
            good_bad = "نتیجه استخاره"

        # سوره و آیه
        m = re.search(r'سوره\s*([^\s<]+).*?آیه\s*(\d+)', text)
        if m:
            chapter = m.group(1)
            ayeh = m.group(2)

        if result_general or good_bad != "نتیجه استخاره":
            lines = [f"🙏 **استخاره از قرآن کریم** (منبع: آوینی)\n"]
            lines.append(f"نتیجه: **{good_bad}**\n")
            if result_general:
                lines.append(f"📜 **کلی:** {result_general}\n")
            if result_marriage:
                lines.append(f"💍 **ازدواج:** {result_marriage}\n")
            if result_trade:
                lines.append(f"💼 **تجارت:** {result_trade}\n")
            if chapter and ayeh:
                lines.append(f"📖 سوره {chapter} — آیه {ayeh}")
            lines.append("\n🔮 با نیت پاک استخاره کنید و به خدا توکل نمایید.")
            return "\n".join(lines)
    except Exception as e:
        logger.error(f"istikhara scrape: {e}")

    # fallback
    random.seed(seed)
    status, desc = random.choice(ISTIKHARA_FALLBACK)
    random.seed()
    return (
        f"🙏 **استخاره**\n\n"
        f"نتیجه: **{status}**\n\n"
        f"{desc}\n\n"
        f"🔮 (منبع موقت — نیت کنید و به خدا توکل نمایید)"
    )


def truth_or_dare() -> str:
    if random.random() < 0.5:
        return f"🔵 **حقیقت**\n\n{random.choice(TRUTH)}"
    return f"🔴 **جرات**\n\n{random.choice(DARE)}"


def joke_of_day() -> str:
    day = datetime.now(tehran_tz).strftime("%Y%m%d")
    random.seed(day + "joke")
    j = random.choice(JOKES)
    random.seed()
    return f"😂 **جوک روز**\n\n{j}"


def fact_of_day() -> str:
    day = datetime.now(tehran_tz).strftime("%Y%m%d")
    random.seed(day + "fact")
    f = random.choice(FACTS)
    random.seed()
    return f"🧠 **دانستنی روز**\n\n{f}"


def daily_challenge() -> str:
    day = datetime.now(tehran_tz).strftime("%Y%m%d")
    random.seed(day + "challenge")
    c = random.choice(CHALLENGES)
    random.seed()
    return f"🎯 **چالش امروز**\n\n{c}\n\n💪 انجامش بده و به خودت افتخار کن!"

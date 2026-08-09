"""استخاره — با مقدمه توحید و صلوات + استخراج از آوینی"""
import random
import hashlib
import re
import httpx
from datetime import datetime
import pytz
from bot.config import config
from bot.logger import logger

tehran_tz = pytz.timezone(config.TIMEZONE)

ISTIKHARA_FALLBACK = [
    ("خوب ✅", "این کار به صلاح شماست. با توکل پیش بروید. ان‌شاءالله نتیجه مطلوب حاصل می‌شود."),
    ("متوسط 🟡", "مصلحت در احتیاط است. عجله نکنید و بیشتر فکر کنید."),
    ("بد ❌", "بهتر است از این کار صرف‌نظر کنید. خیر شما در ترک آن است."),
    ("خوب با تأخیر 🟢", "نتیجه خوب است اما زمان بیشتری نیاز دارد. صبور باشید."),
    ("نیاز به مشورت 🔵", "با افراد آگاه و معتمد مشورت کنید سپس تصمیم بگیرید."),
    ("بسیار خوب ✅✅", "بسیار خوب است. با توکل به خدا اقدام کنید. ان‌شاءالله به همه اهداف‌تان می‌رسید."),
    ("ترک کنید ❌", "ترک این کار به مصلحت نزدیک‌تر است."),
]


def istikhara_intro() -> str:
    """پیام قبل از استخاره — دستورالعمل"""
    return (
        "🙏 **آماده‌سازی برای استخاره**\n\n"
        "قبل از گرفتن استخاره لطفاً این کارها را انجام دهید:\n\n"
        "1️⃣ **سه بار سوره توحید** بخوانید:\n"
        "بِسْمِ اللَّهِ الرَّحْمَٰنِ الرَّحِيمِ\n"
        "قُلْ هُوَ اللَّهُ أَحَدٌ ۝ اللَّهُ الصَّمَدُ ۝\n"
        "لَمْ يَلِدْ وَلَمْ يُولَدْ ۝ وَلَمْ يَكُن لَّهُ كُفُوًا أَحَدٌ\n\n"
        "2️⃣ **سه بار صلوات** بفرستید:\n"
        "اللَّهُمَّ صَلِّ عَلَى مُحَمَّدٍ وَ آلِ مُحَمَّدٍ\n\n"
        "3️⃣ **دعای استخاره** را بخوانید:\n"
        "اللَّهُمَّ إِنِّي أَسْتَخِيرُكَ بِعِلْمِكَ وَأَسْتَقْدِرُكَ بِقُدْرَتِكَ\n"
        "وَأَسْأَلُكَ مِن فَضْلِكَ الْعَظِيمِ فَإِنَّكَ تَقْدِرُ وَلَا أَقْدِرُ\n"
        "وَتَعْلَمُ وَلَا أَعْلَمُ وَأَنتَ عَلَّامُ الْغُيُوبِ\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "بعد از خواندن، روی دکمه **«استخاره بگیر»** بزنید."
    )


async def istikhara(user_id: int = 0) -> str:
    """استخاره از سایت آوینی با fallback"""
    day = datetime.now(tehran_tz).strftime("%Y%m%d%H")
    seed = int(hashlib.md5(f"{user_id}{day}ist".encode()).hexdigest(), 16)
    page = (seed % 580) + 1

    try:
        url = f"https://old.aviny.com/quran/estekhareh/index2.aspx?page={page}"
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }) as client:
            r = await client.get(url)
            r.raise_for_status()
            text = r.text

        result_general = ""
        result_marriage = ""
        result_trade = ""
        good_bad = "نتیجه استخاره"
        chapter = ""
        ayeh = ""

        m = re.search(r'نتیجه\s*کلی[:\s]*(.+?)(?:</|نتیجه|$)', text, re.DOTALL | re.IGNORECASE)
        if m:
            result_general = re.sub(r'<[^>]+>', '', m.group(1)).strip()[:300]

        m = re.search(r'ازدواج[:\s]*(.+?)(?:</|تجارت|$)', text, re.DOTALL | re.IGNORECASE)
        if m:
            result_marriage = re.sub(r'<[^>]+>', '', m.group(1)).strip()[:200]

        m = re.search(r'تجارت[:\s]*(.+?)(?:</|سوره|$)', text, re.DOTALL | re.IGNORECASE)
        if m:
            result_trade = re.sub(r'<[^>]+>', '', m.group(1)).strip()[:200]

        if any(w in text for w in ["حتما انجام بده", "بسیار خوب", "خوب است"]):
            good_bad = "خوب ✅"
        elif any(w in text for w in ["هرگز انجام نده", "بد است", "ترک کن"]):
            good_bad = "بد ❌"
        elif "متوسط" in text or "احتیاط" in text:
            good_bad = "متوسط 🟡"

        m = re.search(r'سوره\s*([^\s<]+).*?آیه\s*(\d+)', text)
        if m:
            chapter = m.group(1)
            ayeh = m.group(2)

        if result_general or good_bad != "نتیجه استخاره":
            lines = [f"🙏 **نتیجه استخاره** (منبع: آوینی)\n"]
            lines.append(f"نتیجه: **{good_bad}**\n")
            if result_general:
                lines.append(f"📜 **کلی:** {result_general}\n")
            if result_marriage:
                lines.append(f"💍 **ازدواج:** {result_marriage}\n")
            if result_trade:
                lines.append(f"💼 **تجارت:** {result_trade}\n")
            if chapter and ayeh:
                lines.append(f"📖 سوره {chapter} — آیه {ayeh}")
            lines.append("\n🔮 با نیت پاک استخاره کردید. به خدا توکل نمایید.")
            return "\n".join(lines)
    except Exception as e:
        logger.error(f"istikhara scrape: {e}")

    random.seed(seed)
    status, desc = random.choice(ISTIKHARA_FALLBACK)
    random.seed()
    return (
        f"🙏 **نتیجه استخاره**\n\n"
        f"نتیجه: **{status}**\n\n"
        f"{desc}\n\n"
        f"🔮 با نیت پاک استخاره کردید. به خدا توکل نمایید."
    )

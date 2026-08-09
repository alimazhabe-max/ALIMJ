"""آیه و حدیث روز — از API رایگان UmmahAPI + fallback محلی"""
import random
import httpx
from datetime import datetime
import pytz
from bot.config import config
from bot.logger import logger

tehran_tz = pytz.timezone(config.TIMEZONE)

LOCAL_VERSES = [
    "﴿إِنَّ مَعَ الْعُسْرِ يُسْرًا﴾ — همانا با سختی آسانی است. (شرح: ۶)",
    "﴿فَاذْكُرُونِي أَذْكُرْكُمْ﴾ — پس مرا یاد کنید تا شما را یاد کنم. (بقره: ۱۵۲)",
    "﴿وَمَن يَتَوَكَّلْ عَلَى اللَّهِ فَهُوَ حَسْبُهُ﴾ — و هر که بر خدا توکل کند، او برایش کافی است. (طلاق: ۳)",
    "﴿لَا يُكَلِّفُ اللَّهُ نَفْسًا إِلَّا وُسْعَهَا﴾ — خدا کسی را جز به اندازه توانش تکلیف نمی‌کند. (بقره: ۲۸۶)",
    "﴿وَبَشِّرِ الصَّابِرِينَ﴾ — و صابران را بشارت ده. (بقره: ۱۵۵)",
    "﴿إِنَّ اللَّهَ مَعَ الصَّابِرِينَ﴾ — همانا خدا با صابران است. (بقره: ۱۵۳)",
    "﴿ادْعُونِي أَسْتَجِبْ لَكُمْ﴾ — مرا بخوانید تا اجابت کنم شما را. (غافر: ۶۰)",
]

LOCAL_HADITHS = [
    "پیامبر (ص): بهترین شما کسی است که اخلاقش نیکوتر باشد.",
    "امام علی (ع): ارزش هر کس به اندازه همت اوست.",
    "پیامبر (ص): تبسم به روی برادر مؤمن صدقه است.",
    "امام صادق (ع): مؤمن آینه مؤمن است.",
    "پیامبر (ص): کسی که به مردم رحم نکند، خدا به او رحم نمی‌کند.",
    "امام علی (ع): سکوت دری از درهای حکمت است.",
]


async def daily_verse_hadith(user_id: int = 0) -> str:
    day = datetime.now(tehran_tz).strftime("%Y%m%d")
    seed = f"{user_id}{day}"

    # سعی در گرفتن آیه تصادفی از API
    verse_text = None
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            # random ayah
            r = await client.get("https://api.alquran.cloud/v1/ayah/random/fa.fooladvand")
            if r.status_code == 200:
                data = r.json().get("data", {})
                ar = data.get("text", "")
                # translation may be in edition
                tr = data.get("edition", {}).get("text") or ""
                surah = data.get("surah", {}).get("name", "")
                num = data.get("numberInSurah", "")
                if ar:
                    verse_text = f"﴿{ar}﴾\n— {surah} آیه {num}"
                    if tr:
                        verse_text += f"\n{tr}"
    except Exception as e:
        logger.error(f"verse api: {e}")

    if not verse_text:
        random.seed(seed + "v")
        verse_text = random.choice(LOCAL_VERSES)
        random.seed()

    random.seed(seed + "h")
    hadith = random.choice(LOCAL_HADITHS)
    random.seed()

    return (
        f"📖 **آیه و حدیث روز**\n\n"
        f"**آیه:**\n{verse_text}\n\n"
        f"**حدیث:**\n{hadith}\n\n"
        f"💚 تدبر کنید."
    )

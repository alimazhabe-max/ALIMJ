"""استخاره بر اساس صفحات قرآن عثمان‌طه (جدول معتبر)"""
import random
import hashlib
from datetime import datetime
import pytz
from bot.config import config
from bot.features.religious.istikhara_data import PAGE_DETAIL

tehran_tz = pytz.timezone(config.TIMEZONE)

# نتیجه کوتاه هر صفحه (صفحات فرد ۱ تا ۶۰۳)
from bot.features.religious.istikhara_data import PAGE_RESULT




def _emoji(res: str) -> str:
    r = res.replace(" ", "")
    if "بسیاربسیارخوب" in r or "بسیار بسیار خوب" in res:
        return "✅✅"
    if "بسیارخوب" in r or "بسیار خوب" in res:
        return "✅"
    if "خوب" in res and "بد" not in res and "میانه" not in res:
        return "🟢"
    if "میانه خوب" in res or "میانه رو به خوب" in res:
        return "🟡🟢"
    if "میانه بد" in res or "میانه رو به بد" in res:
        return "🟡🔴"
    if "میانه" in res:
        return "🟡"
    if "بسیاربسیاربد" in r or "بسیار بسیار بد" in res:
        return "❌❌"
    if "بسیاربد" in r or "بسیار بد" in res:
        return "❌"
    if "بد" in res:
        return "🔴"
    return "🔵"


def istikhara_intro() -> str:
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
        "بعد از خواندن، روی دکمه **«استخاره بگیر»** بزنید.\n"
        "📖 استخاره بر اساس **قرآن عثمان‌طه** (شماره صفحه) انجام می‌شود."
    )


async def istikhara(user_id: int = 0) -> str:
    """استخاره واقعی بر اساس جدول صفحات عثمان‌طه"""
    day = datetime.now(tehran_tz).strftime("%Y%m%d%H%M%S")
    seed = int(hashlib.md5(f"{user_id}{day}uthman".encode()).hexdigest(), 16)
    pages = sorted(PAGE_RESULT.keys())
    page = pages[seed % len(pages)]
    result = PAGE_RESULT.get(page, "میانه")
    detail = PAGE_DETAIL.get(page, "")
    em = _emoji(result)

    text = (
        f"🙏 **نتیجه استخاره** (قرآن عثمان‌طه)\n\n"
        f"📄 صفحه: **{page}**\n"
        f"نتیجه: **{result}** {em}\n\n"
    )
    if detail:
        text += f"📜 **توضیح:**\n{detail}\n\n"
    text += "🔮 با نیت پاک استخاره کردید. به خدا توکل نمایید."
    return text

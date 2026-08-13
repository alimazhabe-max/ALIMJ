"""
قابلیت‌های اضافه دستیار: نمودار، جستجوی وب، کش جواب برای دکمه ویس،
یادآوری زبان‌طبیعی، OCR فیش، و کمک‌کننده‌های استریم.
"""
from __future__ import annotations

import io
import re
import time
import hashlib
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime, timedelta

import pytz

from bot.logger import logger

TEHRAN = pytz.timezone("Asia/Tehran")

# answer_id -> (user_id, text, expires)
_ANSWER_CACHE: Dict[str, Tuple[int, str, float]] = {}
_CACHE_TTL = 3600 * 6


def store_answer(user_id: int, text: str) -> str:
    """ذخیره جواب برای دکمه ویس؛ شناسه کوتاه برمی‌گرداند."""
    aid = hashlib.md5(f"{user_id}:{time.time()}:{text[:80]}".encode()).hexdigest()[:12]
    _ANSWER_CACHE[aid] = (user_id, text, time.time() + _CACHE_TTL)
    # پاکسازی ساده
    if len(_ANSWER_CACHE) > 2000:
        now = time.time()
        dead = [k for k, v in _ANSWER_CACHE.items() if v[2] < now]
        for k in dead[:500]:
            _ANSWER_CACHE.pop(k, None)
    return aid


def get_stored_answer(answer_id: str, user_id: int) -> Optional[str]:
    item = _ANSWER_CACHE.get(answer_id)
    if not item:
        return None
    uid, text, exp = item
    if exp < time.time() or uid != user_id:
        return None
    return text


# ── نمودار ──────────────────────────────────────────────────────────────────

def make_chart_image(
    title: str,
    labels: List[str],
    values: List[float],
    chart_type: str = "bar",
) -> bytes:
    """ساخت تصویر نمودار PNG با matplotlib."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError as e:
        raise RuntimeError("matplotlib نصب نیست. به requirements اضافه کن: matplotlib") from e

    if not labels or not values or len(labels) != len(values):
        raise RuntimeError("برای نمودار به برچسب و عدد هم‌تعداد نیاز است.")

    fig, ax = plt.subplots(figsize=(8, 4.5), dpi=140)
    chart_type = (chart_type or "bar").lower()
    if chart_type == "line":
        ax.plot(labels, values, marker="o", linewidth=2)
    elif chart_type == "pie":
        ax.pie(values, labels=labels, autopct="%1.1f%%", startangle=90)
        ax.axis("equal")
    else:
        ax.bar(labels, values, color="#3b82f6")
        ax.tick_params(axis="x", rotation=30)

    if chart_type != "pie":
        ax.set_title(title or "نمودار")
        ax.grid(True, axis="y", alpha=0.3)
    else:
        ax.set_title(title or "نمودار")

    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf.read()


def parse_chart_request(text: str) -> Optional[Tuple[str, List[str], List[float], str]]:
    """
    تلاش برای فهم درخواست نمودار از متن.
    مثال: نمودار میله‌ای قیمت: دلار 60000، یورو 65000
    """
    t = (text or "").strip()
    if not re.search(r"نمودار|chart|گراف", t, re.I):
        return None
    ctype = "bar"
    if re.search(r"خطی|line", t, re.I):
        ctype = "line"
    elif re.search(r"دایره|pie", t, re.I):
        ctype = "pie"

    # pairs: name number
    pairs = re.findall(
        r"([A-Za-zآ-یء‌]+)\s*[:=：]?\s*([0-9۰-۹]+(?:[.,][0-9۰-۹]+)?)",
        t,
    )
    if len(pairs) < 2:
        return None

    def _num(s: str) -> float:
        s = s.translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")).replace(",", "")
        return float(s)

    labels = [p[0] for p in pairs]
    values = [_num(p[1]) for p in pairs]
    title = "نمودار"
    m = re.search(r"نمودار\s*([^:\n]+)", t)
    if m:
        title = m.group(1).strip()[:60] or title
    return title, labels, values, ctype


# ── جستجوی وب ───────────────────────────────────────────────────────────────

async def web_search(query: str, max_results: int = 5) -> str:
    """جستجوی وب ساده (DuckDuckGo HTML)."""
    query = (query or "").strip()
    if not query:
        return "عبارت جستجو خالی است."
    try:
        import httpx
        from bs4 import BeautifulSoup

        url = "https://html.duckduckgo.com/html/"
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
            r = await client.post(
                url,
                data={"q": query},
                headers={"User-Agent": "Mozilla/5.0 (compatible; RoozeZibaBot/1.0)"},
            )
        soup = BeautifulSoup(r.text, "html.parser")
        results = []
        for a in soup.select("a.result__a")[: max_results]:
            title = a.get_text(" ", strip=True)
            href = a.get("href") or ""
            results.append(f"• {title}\n  {href}")
        if not results:
            # fallback snippets
            for sn in soup.select(".result__snippet")[:max_results]:
                results.append("• " + sn.get_text(" ", strip=True))
        if not results:
            return f"نتیجه‌ای برای «{query}» پیدا نشد."
        return f"نتایج جستجو برای «{query}»:\n\n" + "\n\n".join(results)
    except Exception as e:
        logger.warning("web_search failed: %s", e)
        return f"جستجوی وب ناموفق بود: {e}"


# ── یادآوری زبان طبیعی ─────────────────────────────────────────────────────

def parse_natural_reminder(text: str) -> Optional[Tuple[str, datetime]]:
    """
    استخراج یادآوری از جملات فارسی.
    خروجی: (متن یادآوری, زمان datetime timezone-aware تهران)
    """
    t = (text or "").strip()
    if not re.search(r"یادآوری|یادم\s*بیار|ریمایندر|یادآوری\s*کن|آلارم", t, re.I):
        # الگوهای زمانی هم قبول
        if not re.search(r"فردا|پس‌فردا|ساعت\s*\d|دقیقه\s*دیگه|ساعت\s*دیگه", t, re.I):
            return None
        if not re.search(r"یاد|بگو|خبرم|پیام\s*بده", t, re.I):
            return None

    now = datetime.now(TEHRAN)
    when = None

    # N دقیقه دیگر
    m = re.search(r"(\d+)\s*دقیقه\s*(ی\s*)?(دیگر|دیگه)", t)
    if m:
        when = now + timedelta(minutes=int(m.group(1)))

    # N ساعت دیگر
    if when is None:
        m = re.search(r"(\d+)\s*ساعت\s*(ی\s*)?(دیگر|دیگه)", t)
        if m:
            when = now + timedelta(hours=int(m.group(1)))

    # فردا ساعت H
    if when is None:
        m = re.search(r"فردا(?:\s*ساعت)?\s*(\d{1,2})(?:[:：](\d{2}))?", t)
        if m:
            h = int(m.group(1))
            mi = int(m.group(2) or 0)
            when = (now + timedelta(days=1)).replace(
                hour=min(h, 23), minute=mi, second=0, microsecond=0
            )

    # پس‌فردا
    if when is None and re.search(r"پس\s*فردا", t):
        m = re.search(r"ساعت\s*(\d{1,2})(?:[:：](\d{2}))?", t)
        h = int(m.group(1)) if m else 9
        mi = int(m.group(2)) if m and m.group(2) else 0
        when = (now + timedelta(days=2)).replace(
            hour=min(h, 23), minute=mi, second=0, microsecond=0
        )

    # امروز ساعت H
    if when is None:
        m = re.search(r"(?:امروز\s*)?ساعت\s*(\d{1,2})(?:[:：](\d{2}))?", t)
        if m:
            h = int(m.group(1))
            mi = int(m.group(2) or 0)
            when = now.replace(hour=min(h, 23), minute=mi, second=0, microsecond=0)
            if when <= now:
                when = when + timedelta(days=1)

    if when is None:
        return None

    # متن یادآوری: حذف بخش زمانی
    body = t
    body = re.sub(r"یادآوری(\s*کن)?|یادم\s*بیار|ریمایندر|آلارم", "", body, flags=re.I)
    body = re.sub(
        r"(\d+\s*دقیقه\s*(ی\s*)?(دیگر|دیگه)|\d+\s*ساعت\s*(ی\s*)?(دیگر|دیگه)|"
        r"فردا|پس\s*فردا|امروز|ساعت\s*\d{1,2}(?:[:：]\d{2})?)",
        "",
        body,
        flags=re.I,
    )
    body = re.sub(r"\s+", " ", body).strip(" :、-")
    if not body:
        body = "یادآوری"
    return body[:200], when


# ── OCR فیش (پرامپت تقویت‌شده) ─────────────────────────────────────────────

RECEIPT_OCR_PROMPT = (
    "این تصویر احتمالاً فیش، رسید، فاکتور یا کارت است. "
    "همه متن را با دقت OCR کن و ساخت‌یافته به فارسی برگردان:\n"
    "• فروشنده / فروشگاه\n"
    "• تاریخ و ساعت\n"
    "• اقلام (نام + تعداد + قیمت)\n"
    "• جمع کل / مالیات / تخفیف\n"
    "• شماره پیگیری / مرجع\n"
    "• هر مبلغ یا شماره مهم دیگر\n"
    "اگر خوانا نبود بگو کدام بخش مبهم است. اعداد را دقیق بنویس."
)


def enhance_ocr_prompt(user_prompt: str, has_image: bool) -> str:
    if not has_image:
        return user_prompt
    base = (user_prompt or "").strip()
    if re.search(r"فیش|رسید|فاکتور|OCR|او\s*سی\s*آر|کارت\s*ملی|کارت\s*بانک", base, re.I):
        return RECEIPT_OCR_PROMPT + ("\n\nدرخواست کاربر: " + base if base else "")
    if not base:
        return (
            "تصویر را کامل تحلیل کن. اگر فیش/رسید/متن دارد، متن را دقیق بخوان و "
            "مبالغ و تاریخ را جداگانه لیست کن."
        )
    return base


# ── کیبورد اینلاین زیر جواب AI ───────────────────────────────────────────────

def get_ai_result_keyboard(user_id: int, answer_id: str):
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "🔊 ویس این جواب", callback_data=f"ai_tts:{answer_id}"
                ),
            ],
            [
                InlineKeyboardButton("🌤 هوا", callback_data="ai_quick:weather"),
                InlineKeyboardButton("💰 قیمت", callback_data="ai_quick:price"),
                InlineKeyboardButton("🙏 استخاره", callback_data="ai_quick:istikhara"),
            ],
            [
                InlineKeyboardButton("🕌 اوقات شرعی", callback_data="ai_quick:prayer"),
                InlineKeyboardButton("🧹 حافظه", callback_data="ai_clear_memory"),
            ],
            [
                InlineKeyboardButton(
                    "🎛 انتخاب هوش مصنوعی", callback_data="ai_models"
                ),
            ],
        ]
    )



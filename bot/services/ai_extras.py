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


_LAST_ANSWER: Dict[int, str] = {}


def store_answer(user_id: int, text: str) -> str:
    """ذخیره جواب برای دکمه ویس و درخواست «ویس بفرست»."""
    aid = hashlib.md5(f"{user_id}:{time.time()}:{text[:80]}".encode()).hexdigest()[:12]
    _ANSWER_CACHE[aid] = (user_id, text, time.time() + _CACHE_TTL)
    if text:
        _LAST_ANSWER[user_id] = text
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


def get_last_answer(user_id: int) -> Optional[str]:
    """آخرین جواب AI همین کاربر."""
    return _LAST_ANSWER.get(user_id) or None


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

def parse_natural_reminder(text: str) -> Optional[Tuple[str, datetime, str, int]]:
    """Parse common Persian natural-language reminders.

    Returns: (body, when, repeat_type, repeat_every).
    Supports Persian/Arabic digits and one-time/daily/weekly/monthly/minute/hour repeats.
    """
    t = (text or "").strip()
    if not t:
        return None

    digit_map = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
    t = t.translate(digit_map)
    normalized = t.replace("‌", " ")

    reminder_hint = re.search(
        r"یادآوری|یادم\s*بیار|یادم\s*باشه|یادآوری\s*کن|ریمایندر|آلارم|خبرم\s*کن|پیام\s*بده|یاد\s*بده",
        normalized, re.I,
    )
    time_hint = re.search(
        r"فردا|پس\s*فردا|امروز|ساعت\s*\d|\d+\s*دقیقه\s*(?:دیگه|دیگر)|\d+\s*ساعت\s*(?:دیگه|دیگر)|هر\s*(?:روز|هفته|ماه|\d+\s*(?:دقیقه|ساعت))",
        normalized, re.I,
    )
    if not reminder_hint and not time_hint:
        return None

    now = datetime.now(TEHRAN)
    when: Optional[datetime] = None
    repeat_type = "once"
    repeat_every = 0

    if re.search(r"هر\s*روز|روزانه|daily", normalized, re.I):
        repeat_type, repeat_every = "daily", 1
    elif re.search(r"هر\s*هفته|هفتگی|weekly", normalized, re.I):
        repeat_type, repeat_every = "weekly", 1
    elif re.search(r"هر\s*ماه|ماهانه|monthly", normalized, re.I):
        repeat_type, repeat_every = "monthly", 1
    else:
        m = re.search(r"هر\s*(\d+)\s*دقیقه", normalized, re.I)
        if m:
            repeat_type, repeat_every = "every_minutes", max(1, int(m.group(1)))
        else:
            m = re.search(r"هر\s*(\d+)\s*ساعت", normalized, re.I)
            if m:
                repeat_type, repeat_every = "every_hours", max(1, int(m.group(1)))

    def _hm() -> Optional[tuple[int, int]]:
        m = re.search(r"ساعت\s*(\d{1,2})(?:\s*[:：]\s*(\d{1,2}))?", normalized, re.I)
        if not m:
            return None
        return min(23, int(m.group(1))), min(59, int(m.group(2) or 0))

    m = re.search(r"(\d+)\s*دقیقه\s*(?:دیگه|دیگر)", normalized, re.I)
    if m:
        when = now + timedelta(minutes=max(1, int(m.group(1))))

    if when is None:
        m = re.search(r"(\d+)\s*ساعت\s*(?:دیگه|دیگر)", normalized, re.I)
        if m:
            when = now + timedelta(hours=max(1, int(m.group(1))))

    if when is None and re.search(r"پس\s*فردا", normalized, re.I):
        hm = _hm() or (9, 0)
        when = (now + timedelta(days=2)).replace(hour=hm[0], minute=hm[1], second=0, microsecond=0)

    if when is None and re.search(r"فردا", normalized, re.I):
        hm = _hm() or (9, 0)
        when = (now + timedelta(days=1)).replace(hour=hm[0], minute=hm[1], second=0, microsecond=0)

    if when is None:
        hm = _hm()
        if hm:
            when = now.replace(hour=hm[0], minute=hm[1], second=0, microsecond=0)
            if when <= now:
                when += timedelta(days=1)

    if when is None and repeat_type == "every_minutes":
        when = now + timedelta(minutes=repeat_every)
    elif when is None and repeat_type == "every_hours":
        when = now + timedelta(hours=repeat_every)
    elif when is None and repeat_type != "once":
        when = now + timedelta(minutes=1)

    if when is None:
        return None

    body = normalized
    body = re.sub(r"یادآوری(?:\s*کن)?|یادم\s*(?:بیار|باشه)|ریمایندر|آلارم|خبرم\s*کن|یاد\s*بده", "", body, flags=re.I)
    body = re.sub(
        r"(?:\d+\s*دقیقه\s*(?:دیگه|دیگر)|\d+\s*ساعت\s*(?:دیگه|دیگر)|فردا|پس\s*فردا|امروز|ساعت\s*\d{1,2}(?:\s*[:：]\s*\d{1,2})?|هر\s*روز|روزانه|هر\s*هفته|هفتگی|هر\s*ماه|ماهانه|هر\s*\d+\s*دقیقه|هر\s*\d+\s*ساعت|daily|weekly|monthly)",
        "", body, flags=re.I,
    )
    body = re.sub(r"\s+", " ", body).strip(" :،,-") or "یادآوری"
    return body[:200], when, repeat_type, repeat_every


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
    """زیر جواب AI و ویس هیچ دکمه‌ای نباشد."""
    return None



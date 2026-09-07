"""Shopping Assistant V2 orchestration layer.

این فایل لایه تصمیم‌گیری خرید است و هسته جستجو در shopping.py باقی می‌ماند.
هدف: تبدیل درخواست طبیعی کاربر به یک جستجوی دقیق، سریع و قابل توضیح.
"""

from __future__ import annotations

import re
from typing import Any

from bot.features.market.shopping import search_shopping, shopping_price_history


def normalize_product_query(text: str) -> str:
    text = str(text or "").strip()
    text = text.translate(str.maketrans("يىكۀة‌", "ییکهه "))
    text = re.sub(r"\s+", " ", text)
    # کلمات صرفاً دستوری را از Query حذف می‌کنیم؛ مشخصات محصول باقی می‌ماند.
    text = re.sub(
        r"\b(?:لطفا|لطفاً|میشه|میشود|می.?تونی|پیدا کن|پیدا کنید|برام|برای من|"
        r"بگرد|جستجو کن|جست.?وجو کن|نشون بده|نشان بده)\b",
        " ",
        text,
        flags=re.I,
    )
    return re.sub(r"\s+", " ", text).strip(" ،,.")


def detect_intent(text: str) -> str:
    q = normalize_product_query(text).lower()
    if re.search(r"ارزان(?:ترین)?|کمترین قیمت|ارزان.?تر|cheapest", q):
        return "cheapest"
    if re.search(r"مقایسه|مقایسه کن|compare|مقایسه قیمت", q):
        return "compare"
    if re.search(r"بهترین|معتبرترین|قابل اعتماد|best", q):
        return "best"
    if re.search(r"تاریخچه|هفته قبل|ماه قبل|روند قیمت|افت قیمت", q):
        return "history"
    if re.search(r"اینستاگرام|اینستا|شاپ", q):
        return "instagram"
    return "search"


def extract_budget(text: str) -> tuple[int, int]:
    q = text.translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789"))
    min_price = max_price = 0

    m = re.search(r"(?:از|حداقل)\s*([\d,٬]+)\s*(?:تومان|تومن)?", q)
    if m:
        min_price = int(re.sub(r"[^\d]", "", m.group(1)))

    m = re.search(r"(?:تا|حداکثر|زیر|کمتر از)\s*([\d,٬]+)\s*(?:تومان|تومن)?", q)
    if m:
        max_price = int(re.sub(r"[^\d]", "", m.group(1)))

    return min_price, max_price


def build_search_queries(text: str) -> list[str]:
    """حداکثر سه Query با ارزش اطلاعاتی بالا."""
    q = normalize_product_query(text)
    if not q:
        return []

    intent = detect_intent(q)
    queries = [q]

    if intent == "cheapest":
        queries.append(f"{q} قیمت فروش")
    elif intent == "compare":
        queries.append(f"{q} قیمت فروشگاه")
    elif intent == "instagram":
        queries.append(f"{q} فروشگاه شاپ")
    elif intent == "best":
        queries.append(f"{q} فروشگاه معتبر")

    # dedupe
    out = []
    seen = set()
    for x in queries:
        k = x.casefold()
        if k not in seen:
            seen.add(k)
            out.append(x)
    return out[:3]


async def shopping_assistant(
    request: str = "",
    source: str = "all",
    max_results: int = 14,
    min_price: int = 0,
    max_price: int = 0,
    user_id: int = 0,
) -> str:
    """مسیر تخصصی خرید: intent + بودجه + جستجو + رتبه‌بندی."""
    request = str(request or "").strip()
    if not request:
        return "درخواست خرید خالی است."

    intent = detect_intent(request)

    if intent == "history":
        days_match = re.search(r"(\d+)\s*روز", request)
        days = int(days_match.group(1)) if days_match else 30
        return shopping_price_history(
            query=normalize_product_query(request),
            days=max(1, min(days, 3650)),
            user_id=user_id,
        )

    q_min, q_max = extract_budget(request)
    min_price = int(min_price or q_min or 0)
    max_price = int(max_price or q_max or 0)

    queries = build_search_queries(request)
    if not queries:
        return "نتوانستم نام محصول را از درخواست استخراج کنم."

    # Query اول معمولاً کافی است؛ فقط وقتی نتیجه ضعیف باشد خود search_shopping
    # با fallback خودش کار را ادامه می‌دهد. اینجا عمداً چند بار search نمی‌زنیم
    # تا latency بالا نرود.
    primary = queries[0]

    if intent == "instagram":
        source = "instagram" if source == "all" else source

    result = await search_shopping(
        query=primary,
        source=source,
        max_results=max_results,
        min_price=min_price,
        max_price=max_price,
        user_id=user_id,
    )

    # سربرگ تصمیم‌گیری برای AI: ابزار اصلی همچنان خروجی خرید را تولید می‌کند.
    if intent == "cheapest":
        return "حالت درخواست: ارزان‌ترین با تطابق محصول.\\n\\n" + result
    if intent == "best":
        return "حالت درخواست: بهترین/معتبرترین تطابق.\\n\\n" + result
    if intent == "compare":
        return "حالت درخواست: مقایسه فروشگاه‌ها و قیمت‌ها.\\n\\n" + result
    if intent == "instagram":
        return "حالت درخواست: کشف فروشنده اینستاگرامی؛ قیمت عمومی ممکن است قابل تأیید نباشد.\\n\\n" + result

    return result


__all__ = [
    "shopping_assistant",
    "normalize_product_query",
    "detect_intent",
    "extract_budget",
    "build_search_queries",
]

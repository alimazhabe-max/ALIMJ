"""هوش خرید بازار: جستجوی چندفروشگاهی، تطبیق محصول و استخراج قیمت/لینک.

این ماژول به API خصوصی/غیرمستند یک فروشگاه وابسته نیست. ابتدا موتور جستجو را
برای فروشگاه‌های هدف بررسی می‌کند و سپس صفحه محصول را برای داده‌های ساختاریافته
(Product/Offer/OpenGraph) می‌خواند. به این ترتیب با تغییرات کوچک سایت‌ها مقاوم‌تر است.
"""
from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass, asdict
from typing import Any
from urllib.parse import quote_plus, urlparse

import httpx
from bs4 import BeautifulSoup

from bot.logger import logger

UA = "Mozilla/5.0 (compatible; RoozeZibaBot/2.0; +https://example.com/bot)"
SEARCH_URL = "https://html.duckduckgo.com/html/"
CACHE: dict[str, tuple[float, str]] = {}
CACHE_TTL = 120

SOURCES = {
    "torob": {"label": "ترب", "domains": ["torob.com"]},
    "digikala": {"label": "دیجی‌کالا", "domains": ["digikala.com"]},
    "snappshop": {"label": "اسنپ‌شاپ", "domains": ["snappshop.ir"]},
    "technolife": {"label": "تکنولایف", "domains": ["technolife.ir"]},
    "emalls": {"label": "ایمالز", "domains": ["emalls.ir"]},
    "basalam": {"label": "باسلام", "domains": ["basalam.com"]},
    "momtaz": {"label": "مقداد آی‌تی", "domains": ["meghdadit.com"]},
    "kalaoma": {"label": "کالاوما", "domains": ["kalaoma.com"]},
    "19kala": {"label": "19کالا", "domains": ["19kala.com"]},
    "general": {"label": "وب", "domains": []},
}


@dataclass
class ProductResult:
    source: str
    title: str
    url: str
    price: int | None = None
    old_price: int | None = None
    currency: str = "تومان"
    seller: str = ""
    availability: str = ""
    image: str = ""
    match_hint: str = ""


def _norm_digits(s: str) -> str:
    return str(s).translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789"))


def _price(value: Any) -> int | None:
    if value is None:
        return None
    s = _norm_digits(str(value)).replace("٬", "").replace(",", "").replace(" ", "")
    m = re.search(r"\d+(?:\.\d+)?", s)
    if not m:
        return None
    try:
        n = float(m.group())
    except Exception:
        return None
    # JSON-LD/HTML prices may be rial or toman. Most Iranian stores use تومان
    # in visible text; values with 10x scale are normalized when the currency says ریال.
    return int(n)


def _currency_and_price(raw: Any, currency: str = "") -> tuple[int | None, str]:
    p = _price(raw)
    cur = (currency or "").lower()
    if p is not None and ("rial" in cur or "ریال" in cur):
        p = p // 10
        return p, "تومان"
    if p is not None:
        return p, "تومان"
    return None, "تومان"


def _domain(url: str) -> str:
    try:
        return urlparse(url).netloc.lower().removeprefix("www.")
    except Exception:
        return ""


def _source_for_url(url: str) -> str:
    d = _domain(url)
    for key, cfg in SOURCES.items():
        if any(x in d for x in cfg["domains"]):
            return key
    return "general"


def _clean_title(title: str) -> str:
    title = re.sub(r"\s+", " ", title or "").strip()
    return title[:220]


async def _search(query: str, domain: str = "", limit: int = 6) -> list[dict[str, str]]:
    q = f"site:{domain} {query}" if domain else query
    key = f"search:{q}:{limit}"
    import time
    now = time.time()
    cached = CACHE.get(key)
    if cached and now - cached[0] < CACHE_TTL:
        try:
            return json.loads(cached[1])
        except Exception:
            pass
    async with httpx.AsyncClient(timeout=18, follow_redirects=True, headers={"User-Agent": UA}) as client:
        r = await client.post(SEARCH_URL, data={"q": q})
        r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    out = []
    for a in soup.select("a.result__a")[:limit]:
        href = a.get("href") or ""
        title = _clean_title(a.get_text(" ", strip=True))
        parent = a.find_parent("div", class_="result")
        snippet = ""
        if parent:
            sn = parent.select_one(".result__snippet")
            snippet = sn.get_text(" ", strip=True) if sn else ""
        if href and title:
            out.append({"url": href, "title": title, "snippet": snippet})
    CACHE[key] = (now, json.dumps(out, ensure_ascii=False))
    return out


def _extract_jsonld(soup: BeautifulSoup) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    for tag in soup.select('script[type="application/ld+json"]'):
        try:
            obj = json.loads(tag.string or tag.get_text())
        except Exception:
            continue
        objs = obj if isinstance(obj, list) else [obj]
        for x in objs:
            if isinstance(x, dict):
                if x.get("@type") == "@graph" and isinstance(x.get("@graph"), list):
                    found.extend(y for y in x["@graph"] if isinstance(y, dict))
                else:
                    found.append(x)
    return found


def _from_product(obj: dict[str, Any]) -> tuple[int | None, int | None, str, str, str, str]:
    offers = obj.get("offers") or {}
    if isinstance(offers, list):
        offers = offers[0] if offers else {}
    if not isinstance(offers, dict):
        offers = {}
    price, cur = _currency_and_price(offers.get("price"), offers.get("priceCurrency", ""))
    old = _price(offers.get("highPrice"))
    seller = offers.get("seller")
    if isinstance(seller, dict):
        seller = seller.get("name") or ""
    availability = str(offers.get("availability") or "").split("/")[-1]
    image = obj.get("image") or ""
    if isinstance(image, list):
        image = image[0] if image else ""
    return price, old, str(seller or ""), availability, str(image or ""), cur


async def _inspect(url: str, title: str, snippet: str) -> ProductResult:
    result = ProductResult(source=_source_for_url(url), title=title, url=url, match_hint=snippet[:220])
    try:
        async with httpx.AsyncClient(timeout=14, follow_redirects=True, headers={"User-Agent": UA}) as client:
            r = await client.get(url)
            if r.status_code >= 400:
                return result
        soup = BeautifulSoup(r.text, "html.parser")
        for obj in _extract_jsonld(soup):
            typ = obj.get("@type")
            if typ == "Product" or (isinstance(typ, list) and "Product" in typ):
                p, old, seller, avail, image, cur = _from_product(obj)
                if p is not None:
                    result.price = p
                if old is not None:
                    result.old_price = old
                result.seller = seller
                result.availability = avail
                result.image = image
                result.currency = cur
                break
        if result.price is None:
            # Fallback to common price meta tags / visible Persian price patterns.
            meta = soup.select_one('meta[property="product:price:amount"], meta[itemprop="price"]')
            if meta:
                result.price, result.currency = _currency_and_price(meta.get("content") or meta.get("value"), meta.get("contentCurrency", ""))
        if result.price is None:
            text = soup.get_text(" ", strip=True)
            patterns = [
                r"([0-9۰-۹][0-9۰-۹,٬\.]{3,})\s*(?:تومان|تومن)",
                r"(?:قیمت|Price)\s*[:：]?\s*([0-9۰-۹][0-9۰-۹,٬\.]{3,})",
            ]
            for pat in patterns:
                m = re.search(pat, text, re.I)
                if m:
                    result.price, result.currency = _currency_and_price(m.group(1), "تومان")
                    break
    except Exception as exc:
        logger.debug("shopping inspect failed %s: %s", url, exc)
    return result


def _score(result: ProductResult, query: str) -> float:
    qwords = {x.lower() for x in re.findall(r"[\wآ-ی]{3,}", query)}
    twords = {x.lower() for x in re.findall(r"[\wآ-ی]{3,}", result.title)}
    overlap = len(qwords & twords) / max(1, len(qwords))
    score = overlap * 100
    if result.price is not None:
        score += 5
    if result.seller:
        score += 2
    return score


def _save_history(results: list[ProductResult]) -> None:
    """ذخیره مشاهده قیمت برای نمودار/روند قیمت آینده."""
    if not results:
        return
    try:
        from bot.database import get_db_connection
        import hashlib
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("CREATE TABLE IF NOT EXISTS shopping_price_history (id INTEGER PRIMARY KEY AUTOINCREMENT, product_key TEXT, title TEXT, source TEXT, url TEXT, price INTEGER, captured_at TEXT DEFAULT (datetime('now')))" )
        for x in results:
            if x.price is None:
                continue
            key = hashlib.sha1(re.sub(r"\s+", " ", x.title.lower()).encode("utf-8", "ignore")).hexdigest()[:24]
            c.execute("INSERT INTO shopping_price_history(product_key,title,source,url,price) VALUES(?,?,?,?,?)", (key, x.title[:220], x.source, x.url[:1000], int(x.price)))
        conn.commit()
        conn.close()
    except Exception as exc:
        logger.debug("shopping history save failed: %s", exc)


def shopping_price_history(query: str = "", days: int = 30, user_id: int = 0) -> str:
    """روند قیمت‌های ثبت‌شده برای محصول؛ از داده‌های مشاهده‌شده ربات استفاده می‌کند."""
    query = (query or "").strip()
    if not query:
        return "نام محصول برای تاریخچه قیمت مشخص نیست."
    try:
        from bot.database import get_db_connection
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("CREATE TABLE IF NOT EXISTS shopping_price_history (id INTEGER PRIMARY KEY AUTOINCREMENT, product_key TEXT, title TEXT, source TEXT, url TEXT, price INTEGER, captured_at TEXT DEFAULT (datetime('now')))" )
        words = [w for w in re.findall(r"[\wآ-ی]{3,}", query.lower())][:8]
        rows = c.execute("SELECT title,source,price,captured_at,url FROM shopping_price_history ORDER BY id DESC LIMIT 1000").fetchall()
        conn.close()
        matched=[]
        for row in rows:
            title=str(row[0] or '').lower()
            if not words or sum(w in title for w in words) >= max(1, len(words)//2):
                matched.append(row)
        if not matched:
            return "برای این محصول هنوز تاریخچه قیمتی از جستجوهای قبلی ربات ثبت نشده است."
        prices=[int(r[2]) for r in matched if r[2] is not None]
        lines=[f"📈 تاریخچه مشاهده‌شده قیمت برای «{query}»", f"تعداد مشاهدات: {len(prices)}"]
        if prices:
            lines.append(f"کمترین: {min(prices):,} تومان | بیشترین: {max(prices):,} تومان | میانگین: {sum(prices)/len(prices):,.0f} تومان")
        for r in matched[:10]:
            lines.append(f"• {r[3]} | {SOURCES.get(r[1], SOURCES['general'])['label']} | {int(r[2]):,} تومان")
        return "\n".join(lines)
    except Exception as exc:
        return f"تاریخچه قیمت در دسترس نیست: {exc}"


async def search_shopping(
    query: str = "",
    source: str = "all",
    max_results: int = 12,
    min_price: int = 0,
    max_price: int = 0,
    user_id: int = 0,
) -> str:
    """جستجوی هوشمند قیمت در ترب، دیجی‌کالا و چند فروشگاه ایرانی + وب."""
    query = (query or "").strip()
    if not query:
        return "عبارت محصول برای جستجو مشخص نیست."
    max_results = max(3, min(int(max_results or 12), 18))
    source = (source or "all").lower()
    selected = list(SOURCES) if source in ("all", "همه", "تمام") else [source]
    selected = [s for s in selected if s in SOURCES]
    if "general" not in selected:
        selected.append("general")

    tasks = []
    for key in selected:
        domain = SOURCES[key]["domains"][0] if SOURCES[key]["domains"] else ""
        tasks.append(_search(query, domain, max(4, max_results // max(1, len(selected)) + 2)))
    batches = await asyncio.gather(*tasks, return_exceptions=True)
    links: dict[str, dict[str, str]] = {}
    for batch in batches:
        if isinstance(batch, Exception):
            continue
        for item in batch:
            url = item.get("url", "")
            if url and url not in links:
                links[url] = item

    inspect_tasks = [_inspect(x["url"], x["title"], x.get("snippet", "")) for x in list(links.values())[:24]]
    results = await asyncio.gather(*inspect_tasks, return_exceptions=True)
    clean: list[ProductResult] = []
    for x in results:
        if isinstance(x, ProductResult):
            if min_price and (x.price is None or x.price < min_price):
                continue
            if max_price and x.price is not None and x.price > max_price:
                continue
            clean.append(x)
    clean.sort(key=lambda x: (-_score(x, query), x.price is None, x.price or 10**18))
    clean = clean[:max_results]
    _save_history(clean)

    if not clean:
        # حتی اگر قیمت قابل استخراج نبود، لینک‌های جستجو را بده تا کاربر بن‌بست نداشته باشد.
        fallback = list(links.values())[:max_results]
        if not fallback:
            return f"برای «{query}» نتیجه‌ای پیدا نشد."
        lines = [f"🔎 نتایج خرید برای «{query}» (قیمت در صفحه قابل استخراج نبود):"]
        for i, x in enumerate(fallback, 1):
            lines.append(f"{i}. {x['title']}\n🔗 {x['url']}")
        return "\n\n".join(lines)

    lines = [f"🛒 **نتیجه جستجوی خرید برای «{query}»**", "", "قیمت‌ها از صفحات فروشگاهی در زمان جستجو استخراج شده‌اند؛ موجودی و قیمت نهایی را قبل از خرید بررسی کنید."]
    for i, x in enumerate(clean, 1):
        source_label = SOURCES.get(x.source, SOURCES["general"])["label"]
        price = f"{x.price:,} تومان" if x.price is not None else "قیمت نامشخص"
        extra = []
        if x.old_price and x.old_price > (x.price or 0):
            extra.append(f"قیمت قبلی: {x.old_price:,} تومان")
        if x.seller:
            extra.append(f"فروشنده: {x.seller}")
        if x.availability:
            extra.append(f"وضعیت: {x.availability}")
        lines.append(f"\n{i}. **{x.title}**\n🏪 {source_label} | 💰 {price}")
        if extra:
            lines.append(" | ".join(extra))
        lines.append(f"🔗 {x.url}")
    if clean and all(x.price is not None for x in clean):
        cheapest = min(clean, key=lambda x: x.price or 10**18)
        lines.append(f"\n🏆 ارزان‌ترین نتیجه پیدا‌شده: **{cheapest.price:,} تومان** — {SOURCES.get(cheapest.source, SOURCES['general'])['label']}")
    return "\n".join(lines)

"""Shopping Assistant V2
========================

Drop-in replacement for:
    bot/features/market/shopping.py

هدف:
- کاهش latency با HTTP connection pooling
- جستجوی موازی کنترل‌شده
- cache با TTL و سقف حافظه
- استخراج قیمت از snippet قبل از باز کردن صفحه
- حذف URLهای تکراری و canonicalization
- تطبیق محصول دقیق‌تر (برند/مدل/اعداد/عبارات)
- ranking چندمرحله‌ای
- تشخیص ارزان‌ترین/بهترین/معتبرترین
- fallback هوشمند
- تاریخچه قیمت با فیلتر واقعی بازه زمانی
- استخراج JSON-LD / Meta / متن
- سازگار با API قبلی search_shopping و shopping_price_history

بدون dependency جدید؛ فقط کتابخانه‌های موجود پروژه:
httpx, beautifulsoup4
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import httpx
from bs4 import BeautifulSoup

from bot.logger import logger


UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

SEARCH_URL = "https://html.duckduckgo.com/html/"

# -----------------------------
# Performance tuning
# -----------------------------
CACHE_TTL = 180
CACHE_MAX_ITEMS = 900
SEARCH_CONCURRENCY = 8
INSPECT_CONCURRENCY = 10
SEARCH_TIMEOUT = 12.0
PAGE_TIMEOUT = 10.0
MAX_INSPECT = 28

_search_cache: dict[str, tuple[float, list[dict[str, str]]]] = {}
_http_client: httpx.AsyncClient | None = None
_http_lock: asyncio.Lock | None = None


SOURCES = {
    "torob": {"label": "ترب", "domains": ["torob.com"], "trust": 1.00},
    "digikala": {"label": "دیجی‌کالا", "domains": ["digikala.com"], "trust": 1.00},
    "snappshop": {"label": "اسنپ‌شاپ", "domains": ["snappshop.ir"], "trust": 0.96},
    "emalls": {"label": "ایمالز", "domains": ["emalls.ir"], "trust": 0.98},
    "basalam": {"label": "باسلام", "domains": ["basalam.com"], "trust": 0.90},
    "technolife": {"label": "تکنولایف", "domains": ["technolife.ir"], "trust": 0.96},
    "momtaz": {"label": "مقداد آی‌تی", "domains": ["meghdadit.com"], "trust": 0.94},
    "kalaoma": {"label": "کالاوما", "domains": ["kalaoma.com"], "trust": 0.92},
    "19kala": {"label": "۱۹کالا", "domains": ["19kala.com"], "trust": 0.92},
    "mobile": {"label": "موبایل‌دات‌آی‌آر", "domains": ["mobile.ir"], "trust": 0.86},
    "digistyle": {"label": "دیجی‌استایل", "domains": ["digistyle.com"], "trust": 0.96},
    "modiseh": {"label": "مدیسه", "domains": ["modiseh.com"], "trust": 0.92},
    "zanbil": {"label": "زنبیل", "domains": ["zanbil.ir"], "trust": 0.90},
    "goldiran": {"label": "گلدیران", "domains": ["goldiran.com"], "trust": 0.94},
    "alibaba": {"label": "علی‌بابا", "domains": ["alibaba.ir"], "trust": 0.90},
    "sheypoor": {"label": "شیپور", "domains": ["sheypoor.com"], "trust": 0.74},
    "divar": {"label": "دیوار", "domains": ["divar.ir"], "trust": 0.70},
    "okala": {"label": "اکالا", "domains": ["okala.com"], "trust": 0.90},
    "takhfifan": {"label": "تخفیفان", "domains": ["takhfifan.com"], "trust": 0.82},
    "instagram": {"label": "اینستاگرام", "domains": ["instagram.com"], "trust": 0.66},
    "general": {"label": "وب / سایر", "domains": [], "trust": 0.55},
}

INSTA_KEYWORDS = [
    "فروشگاه", "شاپ", "خرید", "قیمت", "فروش آنلاین",
    "فروشگاه اینترنتی", "خرید آنلاین",
]

BLOCKED_DOMAINS = (
    "youtube.com", "youtu.be", "twitter.com", "x.com", "facebook.com",
    "t.me", "telegram.", "wikipedia.org", "aparat.com",
)

SHOPPING_WORDS = {
    "خرید", "قیمت", "فروشگاه", "فروش", "ارزان", "ارزانترین", "ارزان‌ترین",
    "بهترین", "معتبر", "مقایسه", "لینک", "shop", "buy", "price",
}

PERSIAN_MAP = str.maketrans(
    "يىكۀةؤإأٱ‌",
    "ییکههؤااا "
)


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
    score: float = 0.0
    confidence: float = 0.0
    inspected: bool = False


def _now() -> float:
    return time.monotonic()


def _norm_text(value: Any) -> str:
    s = str(value or "").translate(PERSIAN_MAP).lower()
    s = re.sub(r"[^\wآ-ی]+", " ", s, flags=re.UNICODE)
    return re.sub(r"\s+", " ", s).strip()


def _norm_digits(s: str) -> str:
    return str(s).translate(
        str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
    )


def _price(value: Any) -> int | None:
    if value is None:
        return None
    s = _norm_digits(str(value))
    s = s.replace("٬", "").replace(",", "").replace(" ", "")
    m = re.search(r"\d+(?:\.\d+)?", s)
    if not m:
        return None
    try:
        n = float(m.group())
    except (TypeError, ValueError):
        return None
    if n <= 0:
        return None
    return int(n)


def _currency_and_price(raw: Any, currency: str = "") -> tuple[int | None, str]:
    p = _price(raw)
    cur = str(currency or "").lower()
    if p is not None and ("rial" in cur or "ریال" in cur):
        return p // 10, "تومان"
    return p, "تومان"


def _domain(url: str) -> str:
    try:
        return urlparse(url).netloc.lower().removeprefix("www.")
    except Exception:
        return ""


def _source_for_url(url: str) -> str:
    d = _domain(url)
    for key, cfg in SOURCES.items():
        if any(d == x or d.endswith("." + x) for x in cfg["domains"]):
            return key
    return "general"


def _clean_title(title: str) -> str:
    title = re.sub(r"\s+", " ", title or "").strip()
    return title[:260]


def _canonical_url(url: str) -> str:
    """حذف tracking parameters و fragment برای dedupe بهتر."""
    try:
        p = urlparse(url)
        if not p.scheme:
            return url
        keep = []
        for k, v in parse_qsl(p.query, keep_blank_values=True):
            lk = k.lower()
            if lk.startswith("utm_") or lk in {
                "fbclid", "gclid", "ref", "ref_", "source", "campaign"
            }:
                continue
            keep.append((k, v))
        return urlunparse(
            (p.scheme, p.netloc.lower(), p.path.rstrip("/") or "/",
             p.params, urlencode(keep), "")
        )
    except Exception:
        return url


def _cache_get(key: str) -> list[dict[str, str]] | None:
    item = _search_cache.get(key)
    if not item:
        return None
    ts, value = item
    if _now() - ts >= CACHE_TTL:
        _search_cache.pop(key, None)
        return None
    return list(value)


def _cache_put(key: str, value: list[dict[str, str]]) -> None:
    if len(_search_cache) >= CACHE_MAX_ITEMS:
        # حذف حدود 10٪ از قدیمی‌ترین آیتم‌ها
        old = sorted(_search_cache.items(), key=lambda kv: kv[1][0])
        for k, _ in old[: max(1, CACHE_MAX_ITEMS // 10)]:
            _search_cache.pop(k, None)
    _search_cache[key] = (_now(), list(value))


async def _get_client() -> httpx.AsyncClient:
    global _http_client, _http_lock
    if _http_client is not None:
        return _http_client
    if _http_lock is None:
        _http_lock = asyncio.Lock()
    async with _http_lock:
        if _http_client is None:
            limits = httpx.Limits(
                max_connections=20,
                max_keepalive_connections=12,
                keepalive_expiry=30,
            )
            _http_client = httpx.AsyncClient(
                timeout=httpx.Timeout(PAGE_TIMEOUT, connect=5.0),
                follow_redirects=True,
                headers={
                    "User-Agent": UA,
                    "Accept-Language": "fa-IR,fa;q=0.9,en;q=0.7",
                    "Accept": "text/html,application/xhtml+xml",
                },
                limits=limits,
            )
    return _http_client


async def close_shopping_client() -> None:
    global _http_client
    if _http_client is not None:
        try:
            await _http_client.aclose()
        finally:
            _http_client = None


async def _search(
    query: str,
    domain: str = "",
    limit: int = 8,
    extra: str = "",
) -> list[dict[str, str]]:
    parts = []
    if domain:
        parts.append(f"site:{domain}")
    parts.append(query)
    if extra:
        parts.append(extra)
    q = " ".join(parts).strip()

    key = f"search:{_norm_text(q)}:{int(limit)}"
    cached = _cache_get(key)
    if cached is not None:
        return cached

    try:
        client = await _get_client()
        r = await client.post(
            SEARCH_URL,
            data={"q": q},
            timeout=SEARCH_TIMEOUT,
        )
        r.raise_for_status()

        soup = BeautifulSoup(r.text, "html.parser")
        out: list[dict[str, str]] = []

        for a in soup.select("a.result__a")[:limit]:
            href = (a.get("href") or "").strip()
            title = _clean_title(a.get_text(" ", strip=True))
            parent = a.find_parent("div", class_="result")
            snippet = ""
            if parent:
                sn = parent.select_one(".result__snippet")
                snippet = sn.get_text(" ", strip=True) if sn else ""

            if href and title:
                out.append({
                    "url": _canonical_url(href),
                    "title": title,
                    "snippet": _clean_title(snippet),
                })

        _cache_put(key, out)
        return out
    except Exception as exc:
        logger.debug("shopping search failed for %s: %s", q, exc)
        return []


def _extract_prices_from_text(text: str) -> list[int]:
    text = _norm_digits(text or "")
    patterns = [
        r"(\d{1,3}(?:[,\u066c]\d{3})+(?:\.\d+)?)\s*(?:تومان|تومن|ت\.?م)",
        r"(?:قیمت|قیمت نهایی|قیمت فروش|price)\s*[:：]?\s*(\d{2,}(?:[,\u066c]\d{3})*)",
        r"(\d{4,})\s*(?:تومان|تومن|ت\.?م)",
    ]
    found: list[int] = []
    for pat in patterns:
        for m in re.finditer(pat, text, re.I):
            p = _price(m.group(1))
            if p is not None:
                found.append(p)
    return found


def _extract_snippet_price(title: str, snippet: str) -> int | None:
    combined = f"{title} {snippet}"
    prices = _extract_prices_from_text(combined)
    if not prices:
        return None

    # قیمت‌هایی که نزدیک کلمه قیمت/تومان هستند اولویت دارند.
    norm = _norm_digits(combined)
    if re.search(r"(قیمت|price|تومان|تومن)", norm, re.I):
        return min(prices)
    return prices[0]


def _extract_jsonld(soup: BeautifulSoup) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []

    def add(obj: Any) -> None:
        if isinstance(obj, list):
            for x in obj:
                add(x)
            return
        if not isinstance(obj, dict):
            return

        typ = obj.get("@type")
        if typ == "@graph" and isinstance(obj.get("@graph"), list):
            add(obj["@graph"])
            return
        found.append(obj)

    for tag in soup.select('script[type="application/ld+json"]'):
        raw = tag.string or tag.get_text()
        if not raw:
            continue
        try:
            add(json.loads(raw))
        except Exception:
            continue
    return found


def _from_product(
    obj: dict[str, Any],
) -> tuple[int | None, int | None, str, str, str, str]:
    offers = obj.get("offers") or {}
    if isinstance(offers, list):
        offers = offers[0] if offers else {}
    if not isinstance(offers, dict):
        offers = {}

    price, cur = _currency_and_price(
        offers.get("price") or offers.get("lowPrice"),
        offers.get("priceCurrency", ""),
    )

    old = _price(offers.get("highPrice"))
    if old is not None and price is not None and old <= price:
        old = None

    seller = offers.get("seller")
    if isinstance(seller, dict):
        seller = seller.get("name") or ""

    availability = str(offers.get("availability") or "").split("/")[-1]

    image = obj.get("image") or ""
    if isinstance(image, list):
        image = image[0] if image else ""

    return (
        price,
        old,
        str(seller or ""),
        availability,
        str(image or ""),
        cur,
    )


def _extract_meta(soup: BeautifulSoup) -> tuple[int | None, str, str]:
    amount = soup.select_one(
        'meta[property="product:price:amount"], '
        'meta[itemprop="price"], '
        'meta[property="og:price:amount"]'
    )
    currency = soup.select_one(
        'meta[property="product:price:currency"], '
        'meta[itemprop="priceCurrency"]'
    )

    if not amount:
        return None, "تومان", ""

    p, cur = _currency_and_price(
        amount.get("content") or amount.get("value"),
        currency.get("content") if currency else "",
    )
    return p, cur, ""


async def _inspect(
    url: str,
    title: str,
    snippet: str,
) -> ProductResult:
    result = ProductResult(
        source=_source_for_url(url),
        title=_clean_title(title),
        url=url,
        match_hint=_clean_title(snippet)[:240],
    )

    # اینستاگرام: قیمت عمومی قابل اتکا نیست؛ صفحه را بی‌دلیل fetch نکن.
    if result.source == "instagram":
        result.seller = "صفحه اینستاگرامی"
        result.price = _extract_snippet_price(title, snippet)
        result.inspected = False
        return result

    # قیمت snippet را فعلاً نگه می‌داریم و فقط اگر صفحه قیمت دقیق‌تری داد جایگزین می‌کنیم.
    snippet_price = _extract_snippet_price(title, snippet)
    if snippet_price is not None:
        result.price = snippet_price

    try:
        client = await _get_client()
        r = await client.get(url, timeout=PAGE_TIMEOUT)
        if r.status_code >= 400:
            return result

        result.inspected = True
        soup = BeautifulSoup(r.text, "html.parser")

        # 1) JSON-LD
        for obj in _extract_jsonld(soup):
            typ = obj.get("@type")
            types = typ if isinstance(typ, list) else [typ]
            if "Product" not in types:
                continue

            p, old, seller, avail, image, cur = _from_product(obj)
            if p is not None:
                result.price = p
            if old is not None:
                result.old_price = old
            result.seller = seller or result.seller
            result.availability = avail
            result.image = image
            result.currency = cur

            if result.price is not None:
                break

        # 2) Meta
        if result.price is None:
            p, cur, _ = _extract_meta(soup)
            if p is not None:
                result.price = p
                result.currency = cur

        # 3) متن صفحه
        if result.price is None:
            text = soup.get_text(" ", strip=True)
            prices = _extract_prices_from_text(text[:180_000])
            if prices:
                result.price = min(prices)

        # عنوان بهتر
        og_title = soup.select_one('meta[property="og:title"]')
        if og_title and og_title.get("content"):
            clean = _clean_title(og_title["content"])
            if len(clean) >= 8:
                result.title = clean

        # seller fallback
        if not result.seller:
            seller_meta = soup.select_one(
                'meta[property="product:brand"], meta[itemprop="brand"]'
            )
            if seller_meta:
                result.seller = seller_meta.get("content", "")

    except Exception as exc:
        logger.debug("shopping inspect failed %s: %s", url, exc)

    return result


def _tokens(value: str) -> set[str]:
    return {
        x for x in re.findall(r"[\wآ-ی]{2,}", _norm_text(value))
        if x not in SHOPPING_WORDS
    }


def _numbers(value: str) -> set[str]:
    return set(re.findall(r"\d+(?:\.\d+)?", _norm_digits(value or "")))


def _query_intent(query: str) -> str:
    q = _norm_text(query)
    if re.search(r"ارزان(?:ترین)?|کمترین قیمت|ارزان تر|ارزانتر|cheapest", q):
        return "cheapest"
    if re.search(r"بهترین|best|معتبرترین|معتبر", q):
        return "best"
    return "normal"


def _score(result: ProductResult, query: str) -> float:
    qn = _norm_text(query)
    tn = _norm_text(result.title)
    hint = _norm_text(result.match_hint)

    qwords = _tokens(qn)
    twords = _tokens(tn)
    hwords = _tokens(hint)

    if not qwords:
        return 0.0

    overlap = len(qwords & twords) / max(1, len(qwords))
    hint_overlap = len(qwords & hwords) / max(1, len(qwords))

    score = overlap * 62.0 + hint_overlap * 10.0

    # عبارت کامل مدل/محصول
    if len(qn) >= 5 and qn in tn:
        score += 18.0

    qnums = _numbers(qn)
    tnums = _numbers(tn)
    if qnums:
        matched_nums = len(qnums & tnums)
        score += (matched_nums / len(qnums)) * 28.0
        if matched_nums < len(qnums):
            score -= 18.0

    # وجود قیمت/فروشنده/وضعیت
    if result.price is not None:
        score += 9.0
    if result.seller:
        score += 3.0
    if result.availability:
        score += 2.0

    cfg = SOURCES.get(result.source, SOURCES["general"])
    score += float(cfg.get("trust", 0.5)) * 8.0

    # نتایج عمومی ضعیف‌تر از فروشگاه مشخص
    if result.source == "general":
        score -= 4.0

    # اینستا برای کشف فروشنده خوب است، اما نباید بالاتر از محصول دقیق فروشگاه قرار گیرد.
    if result.source == "instagram":
        score += 1.5

    result.confidence = max(0.0, min(1.0, score / 125.0))
    return score


def _dedupe_results(results: list[ProductResult]) -> list[ProductResult]:
    """یک URL یا محصول تقریباً یکسان را فقط یک بار نگه می‌دارد."""
    by_key: dict[str, ProductResult] = {}

    for x in results:
        title_key = re.sub(r"\W+", " ", _norm_text(x.title))
        key = f"{_canonical_url(x.url)}|{title_key[:120]}"

        # اگر URL یکی است، نتیجه با قیمت/امتیاز بهتر را نگه دار.
        prev = by_key.get(key)
        if prev is None:
            by_key[key] = x
        else:
            prev_value = (
                (1 if prev.price is not None else 0),
                prev.score,
                1 if prev.inspected else 0,
            )
            new_value = (
                (1 if x.price is not None else 0),
                x.score,
                1 if x.inspected else 0,
            )
            if new_value > prev_value:
                by_key[key] = x

    return list(by_key.values())


def _save_history(results: list[ProductResult]) -> None:
    if not results:
        return
    try:
        from bot.database import get_db_connection

        conn = get_db_connection()
        c = conn.cursor()
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS shopping_price_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_key TEXT,
                title TEXT,
                source TEXT,
                url TEXT,
                price INTEGER,
                captured_at TEXT DEFAULT (datetime('now'))
            )
            """
        )

        for x in results:
            if x.price is None:
                continue

            # کلید محصول را از title + source می‌سازیم تا دو محصول مشابه
            # از دو فروشگاه کاملاً با هم قاطی نشوند.
            key_raw = f"{_norm_text(x.title)}|{x.source}"
            key = hashlib.sha1(
                key_raw.encode("utf-8", "ignore")
            ).hexdigest()[:24]

            c.execute(
                """
                INSERT INTO shopping_price_history
                    (product_key,title,source,url,price)
                VALUES (?,?,?,?,?)
                """,
                (
                    key,
                    x.title[:220],
                    x.source,
                    x.url[:1000],
                    int(x.price),
                ),
            )

        conn.commit()
        conn.close()
    except Exception as exc:
        logger.debug("shopping history save failed: %s", exc)


def shopping_price_history(
    query: str = "",
    days: int = 30,
    user_id: int = 0,
) -> str:
    query = (query or "").strip()
    if not query:
        return "نام محصول برای تاریخچه قیمت مشخص نیست."

    days = max(1, min(int(days or 30), 3650))

    try:
        from bot.database import get_db_connection

        conn = get_db_connection()
        c = conn.cursor()

        c.execute(
            """
            CREATE TABLE IF NOT EXISTS shopping_price_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_key TEXT,
                title TEXT,
                source TEXT,
                url TEXT,
                price INTEGER,
                captured_at TEXT DEFAULT (datetime('now'))
            )
            """
        )

        # اینجا days واقعاً روی SQL اعمال می‌شود.
        rows = c.execute(
            """
            SELECT title,source,price,captured_at,url
            FROM shopping_price_history
            WHERE captured_at >= datetime('now', ?)
            ORDER BY id DESC
            LIMIT 2000
            """,
            (f"-{days} days",),
        ).fetchall()

        conn.close()

        words = list(_tokens(query))[:10]
        matched = []

        for row in rows:
            title = str(row[0] or "")
            t = _norm_text(title)
            if not words or sum(w in t for w in words) >= max(1, len(words) // 2):
                matched.append(row)

        if not matched:
            return (
                f"در {days} روز اخیر برای «{query}» "
                "تاریخچه قیمتی از مشاهدات ثبت‌شده ربات وجود ندارد."
            )

        prices = [int(r[2]) for r in matched if r[2] is not None]

        lines = [
            f"📈 تاریخچه قیمت «{query}» در {days} روز اخیر",
            f"تعداد مشاهدات: {len(prices)}",
        ]

        if prices:
            avg = sum(prices) / len(prices)
            lines.append(
                f"کمترین: {min(prices):,} تومان | "
                f"بیشترین: {max(prices):,} تومان | "
                f"میانگین: {avg:,.0f} تومان"
            )

        for r in matched[:15]:
            src = SOURCES.get(r[1], SOURCES["general"])["label"]
            price = int(r[2]) if r[2] is not None else 0
            lines.append(f"• {r[3]} | {src} | {price:,} تومان")

        return "\n".join(lines)

    except Exception as exc:
        logger.debug("shopping history failed: %s", exc)
        return f"تاریخچه قیمت در دسترس نیست: {exc}"


def _select_sources(source: str) -> list[str]:
    source = (source or "all").lower().strip()

    if source in ("all", "همه", "تمام", "everywhere", "web"):
        selected = list(SOURCES.keys())
    else:
        selected = [
            s for s in re.split(r"[\s,]+", source)
            if s in SOURCES
        ]
        if not selected:
            selected = list(SOURCES.keys())

    # این دو منبع همیشه fallback هستند.
    if "general" not in selected:
        selected.append("general")
    if "instagram" not in selected:
        selected.append("instagram")

    return selected


def _build_queries(query: str, key: str) -> list[str]:
    """حداقل Query لازم را می‌سازد؛ نه اینکه برای هر فروشگاه چندین درخواست بفرستد."""
    q = query.strip()

    if key == "instagram":
        return [
            f"{q} فروشگاه",
            f"{q} شاپ خرید",
        ]

    if key == "general":
        return [
            q,
            f"{q} قیمت خرید",
        ]

    # برای فروشگاه مشخص فقط یک درخواست؛ سرعت بسیار بهتر از نسخه قبلی.
    return [q]


async def _run_search_tasks(
    query: str,
    selected: list[str],
    max_results: int,
) -> list[dict[str, str]]:
    sem = asyncio.Semaphore(SEARCH_CONCURRENCY)
    tasks = []

    async def one(key: str, q: str, limit: int) -> list[dict[str, str]]:
        cfg = SOURCES[key]
        domain = cfg["domains"][0] if cfg["domains"] else ""
        async with sem:
            rows = await _search(q, domain=domain, limit=limit)
            for row in rows:
                row["_source_hint"] = key
            return rows

    # برای جلوگیری از انفجار تعداد درخواست‌ها، سهم هر منبع محدود است.
    per_source = max(4, min(7, max_results // max(1, len(selected)) + 3))

    for key in selected:
        for q in _build_queries(query, key):
            limit = per_source + (2 if key in ("general", "instagram") else 0)
            tasks.append(one(key, q, limit))

    batches = await asyncio.gather(*tasks, return_exceptions=True)

    all_rows: list[dict[str, str]] = []
    for batch in batches:
        if isinstance(batch, Exception):
            continue
        all_rows.extend(batch)
    return all_rows


def _rank_raw_candidates(
    rows: list[dict[str, str]],
    query: str,
) -> list[dict[str, str]]:
    seen: set[str] = set()
    out: list[dict[str, str]] = []

    for row in rows:
        url = _canonical_url((row.get("url") or "").strip())
        if not url or url in seen:
            continue
        seen.add(url)

        low = url.lower()
        if any(d in low for d in BLOCKED_DOMAINS):
            continue

        title = _clean_title(row.get("title", ""))
        snippet = _clean_title(row.get("snippet", ""))

        # یک امتیاز اولیه برای اینکه فقط صفحات با پتانسیل بالا fetch شوند.
        raw = ProductResult(
            source=_source_for_url(url),
            title=title,
            url=url,
            match_hint=snippet,
            price=_extract_snippet_price(title, snippet),
        )
        raw.score = _score(raw, query)

        row = dict(row)
        row["url"] = url
        row["title"] = title
        row["snippet"] = snippet
        row["_pre_score"] = str(raw.score)
        out.append(row)

    out.sort(key=lambda x: float(x.get("_pre_score", "0")), reverse=True)
    return out


async def _inspect_candidates(
    candidates: list[dict[str, str]],
) -> list[ProductResult]:
    sem = asyncio.Semaphore(INSPECT_CONCURRENCY)

    async def one(x: dict[str, str]) -> ProductResult:
        async with sem:
            return await _inspect(
                x["url"],
                x["title"],
                x.get("snippet", ""),
            )

    return [
        x for x in await asyncio.gather(
            *(one(c) for c in candidates),
            return_exceptions=True,
        )
        if isinstance(x, ProductResult)
    ]


def _format_result(x: ProductResult, index: int) -> list[str]:
    label = SOURCES.get(x.source, SOURCES["general"])["label"]

    if x.price is None:
        price = (
            "قیمت عمومی مشخص نشد"
            if x.source != "instagram"
            else "قیمت عمومی در اینستاگرام قابل اتکا نیست"
        )
    else:
        price = f"{x.price:,} تومان"

    lines = [f"{index}. **{x.title}**"]
    lines.append(f"🏪 {label} | 💰 {price}")

    extra = []
    if x.old_price and x.old_price > (x.price or 0):
        extra.append(f"قبلی: {x.old_price:,}")
    if x.seller:
        extra.append(f"فروشنده: {x.seller}")
    if x.availability:
        extra.append(f"وضعیت: {x.availability}")
    if x.confidence:
        extra.append(f"تطابق: {round(x.confidence * 100)}٪")

    if extra:
        lines.append(" · ".join(extra))

    lines.append(f"🔗 {x.url}")
    return lines


async def search_shopping(
    query: str = "",
    source: str = "all",
    max_results: int = 14,
    min_price: int = 0,
    max_price: int = 0,
    user_id: int = 0,
) -> str:
    """جستجوی سریع و دقیق خرید در فروشگاه‌ها + اینستاگرام + وب."""

    query = (query or "").strip()
    if not query:
        return "عبارت محصول برای جستجو مشخص نیست."

    max_results = max(4, min(int(max_results or 14), 22))
    min_price = max(0, int(min_price or 0))
    max_price = max(0, int(max_price or 0))

    selected = _select_sources(source)
    intent = _query_intent(query)

    # -----------------------------
    # Pass 1: Search
    # -----------------------------
    rows = await _run_search_tasks(query, selected, max_results)

    if not rows:
        return f"برای «{query}» در منابع انتخاب‌شده نتیجه‌ای پیدا نشد."

    ranked_rows = _rank_raw_candidates(rows, query)

    # ابتدا نتایجی که snippet قیمت دارند؛ سپس نتایج قوی بدون قیمت.
    # این کار تعداد fetchهای سنگین را پایین می‌آورد.
    with_price = [
        r for r in ranked_rows
        if _extract_snippet_price(r.get("title", ""), r.get("snippet", "")) is not None
    ]
    without_price = [
        r for r in ranked_rows
        if r not in with_price
    ]

    # سقف واقعی fetchها
    candidate_pool = (with_price + without_price)[:MAX_INSPECT]

    # -----------------------------
    # Pass 2: Inspect
    # -----------------------------
    results = await _inspect_candidates(candidate_pool)

    clean: list[ProductResult] = []
    for x in results:
        if min_price and (x.price is None or x.price < min_price):
            continue
        if max_price and x.price is not None and x.price > max_price:
            continue

        x.score = _score(x, query)
        clean.append(x)

    clean = _dedupe_results(clean)

    # نتایج خیلی نامرتبط را در صورت وجود گزینه‌های بهتر حذف کن.
    strong = [x for x in clean if x.score >= 25]
    if strong:
        clean = strong

    # ranking نهایی
    if intent == "cheapest":
        # تطابق محصول مهم‌تر از صرفاً کمترین قیمت است.
        clean.sort(
            key=lambda x: (
                -x.score,
                x.price is None,
                x.price or 10**18,
            )
        )
        # در بین نتایج با تطابق کافی، ارزان‌ترین‌ها بالا می‌آیند.
        clean = sorted(
            clean,
            key=lambda x: (
                0 if x.score >= 55 and x.price is not None else 1,
                x.price is None,
                x.price or 10**18,
                -x.score,
            ),
        )
    elif intent == "best":
        clean.sort(
            key=lambda x: (
                -x.score,
                x.price is None,
                x.price or 10**18,
            )
        )
    else:
        clean.sort(
            key=lambda x: (
                -x.score,
                x.price is None,
                x.price or 10**18,
            )
        )

    clean = clean[:max_results]

    _save_history(clean)

    # -----------------------------
    # Fallback
    # -----------------------------
    if not clean:
        fallback = ranked_rows[:max_results]
        if not fallback:
            return f"برای «{query}» نتیجه‌ای پیدا نشد."

        lines = [
            f"🔎 نتایج جستجو برای «{query}»",
            "قیمت قطعی از صفحات استخراج نشد؛ لینک‌ها برای بررسی دستی:",
            "",
        ]
        for i, x in enumerate(fallback, 1):
            src = _source_for_url(x["url"])
            label = SOURCES.get(src, SOURCES["general"])["label"]
            lines.extend([
                f"{i}. **{x['title']}**",
                f"🏪 {label}",
                f"🔗 {x['url']}",
                "",
            ])
        return "\n".join(lines)

    # -----------------------------
    # Final response
    # -----------------------------
    lines = [
        f"🛒 **نتیجه جستجوی هوشمند برای «{query}»**",
        "",
        f"منابع بررسی‌شده: {len(selected)} منبع | "
        f"نتایج اولیه: {len(ranked_rows)} | صفحات بررسی‌شده: {len(candidate_pool)}",
        "قیمت‌ها از داده‌های قابل مشاهده استخراج شده‌اند؛ قبل از پرداخت قیمت و موجودی نهایی را بررسی کنید.",
        "",
    ]

    for i, x in enumerate(clean, 1):
        lines.extend(_format_result(x, i))
        lines.append("")

    priced = [
        x for x in clean
        if x.price is not None and x.score >= 45
    ]

    if priced:
        cheapest = min(priced, key=lambda x: x.price or 10**18)
        cheapest_label = SOURCES.get(
            cheapest.source, SOURCES["general"]
        )["label"]

        lines.append(
            f"🏆 **ارزان‌ترین نتیجه با تطابق قابل قبول:** "
            f"{cheapest.price:,} تومان — {cheapest_label}"
        )

        best = max(priced, key=lambda x: x.score)
        best_label = SOURCES.get(best.source, SOURCES["general"])["label"]
        lines.append(
            f"🎯 **بهترین تطابق محصول:** "
            f"{best.title[:100]} — {best_label}"
        )

        if len(priced) >= 2:
            vals = [x.price for x in priced if x.price is not None]
            spread = max(vals) - min(vals)
            if spread > 0:
                lines.append(
                    f"📉 اختلاف کمترین و بیشترین قیمت در نتایج معتبر: "
                    f"{spread:,} تومان"
                )

    source_counts: dict[str, int] = {}
    for x in clean:
        source_counts[x.source] = source_counts.get(x.source, 0) + 1

    if source_counts:
        summary = " · ".join(
            f"{SOURCES.get(k, SOURCES['general'])['label']}: {v}"
            for k, v in sorted(
                source_counts.items(),
                key=lambda item: -item[1],
            )
        )
        lines.append(f"\n📊 منابع نتایج: {summary}")

    return "\n".join(lines)


__all__ = [
    "ProductResult",
    "SOURCES",
    "search_shopping",
    "shopping_price_history",
    "close_shopping_client",
]

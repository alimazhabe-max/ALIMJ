"""هوش خرید بازار: جستجوی گسترده چندفروشگاهی + اینستاگرام + کل وب.

این ماژول به API خصوصی فروشگاه‌ها وابسته نیست. از موتور جستجو (DuckDuckGo)
برای فروشگاه‌های هدف، اینستاگرام و کل اینترنت استفاده می‌کند و سپس صفحه را
برای داده‌های ساختاریافته (JSON-LD Product/Offer) و الگوهای قیمت فارسی می‌خواند.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import re
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote_plus, urlparse

import httpx
from bs4 import BeautifulSoup

from bot.logger import logger

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)
SEARCH_URL = "https://html.duckduckgo.com/html/"
CACHE: dict[str, tuple[float, str]] = {}
CACHE_TTL = 300

# لیست گسترده فروشگاه‌ها و منابع ایرانی + بین‌المللی مرتبط
SOURCES = {
    # مقایسه قیمت و مارکت‌پلیس‌های اصلی
    "torob": {"label": "ترب", "domains": ["torob.com"]},
    "digikala": {"label": "دیجی‌کالا", "domains": ["digikala.com"]},
    "snappshop": {"label": "اسنپ‌شاپ", "domains": ["snappshop.ir"]},
    "emalls": {"label": "ایمالز", "domains": ["emalls.ir"]},
    "basalam": {"label": "باسلام", "domains": ["basalam.com"]},
    # تخصصی تکنولوژی و موبایل
    "technolife": {"label": "تکنولایف", "domains": ["technolife.ir"]},
    "momtaz": {"label": "مقداد آی‌تی", "domains": ["meghdadit.com"]},
    "kalaoma": {"label": "کالاوما", "domains": ["kalaoma.com"]},
    "19kala": {"label": "۱۹کالا", "domains": ["19kala.com"]},
    "mobile": {"label": "موبایل‌دات‌آی‌آر", "domains": ["mobile.ir"]},
    "digistyle": {"label": "دیجی‌استایل", "domains": ["digistyle.com"]},
    # مد و پوشاک و زیبایی
    "modiseh": {"label": "مدیسه", "domains": ["modiseh.com"]},
    "zanbil": {"label": "زنبیل", "domains": ["zanbil.ir"]},
    "goldiran": {"label": "گلدیران", "domains": ["goldiran.com"]},
    # مارکت‌پلیس و عمومی
    "alibaba": {"label": "علی‌بابا", "domains": ["alibaba.ir"]},
    "sheypoor": {"label": "شیپور", "domains": ["sheypoor.com"]},
    "divar": {"label": "دیوار", "domains": ["divar.ir"]},
    "okala": {"label": "اکالا", "domains": ["okala.com"]},
    "takhfifan": {"label": "تخفیفان", "domains": ["takhfifan.com"]},
    # اینستاگرام و شبکه‌های اجتماعی
    "instagram": {"label": "اینستاگرام", "domains": ["instagram.com"]},
    # جستجوی عمومی وب (همه‌جا)
    "general": {"label": "وب / سایر", "domains": []},
}

# کلمات کلیدی برای تقویت جستجوی اینستاگرام و فروشگاه‌های آنلاین
INSTA_KEYWORDS = [
    "فروشگاه", "شاپ", "خرید", "قیمت", "فروش آنلاین", "online shop",
    "فروشگاه اینترنتی", "خرید آنلاین",
]


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
    return str(s).translate(
        str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
    )


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
    return title[:240]


async def _search(query: str, domain: str = "", limit: int = 8, extra: str = "") -> list[dict[str, str]]:
    """جستجو در DuckDuckGo با امکان محدود کردن به دامنه یا عبارت اضافه."""
    parts = []
    if domain:
        parts.append(f"site:{domain}")
    parts.append(query)
    if extra:
        parts.append(extra)
    q = " ".join(parts)

    key = f"search:{q}:{limit}"
    now = time.time()
    cached = CACHE.get(key)
    if cached and now - cached[0] < CACHE_TTL:
        try:
            return json.loads(cached[1])
        except Exception:
            pass

    try:
        async with httpx.AsyncClient(
            timeout=20, follow_redirects=True, headers={"User-Agent": UA}
        ) as client:
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
    except Exception as exc:
        logger.debug("shopping search failed for %s: %s", q, exc)
        return []


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
    price, cur = _currency_and_price(
        offers.get("price") or offers.get("lowPrice"),
        offers.get("priceCurrency", ""),
    )
    old = _price(offers.get("highPrice") or offers.get("price"))
    seller = offers.get("seller")
    if isinstance(seller, dict):
        seller = seller.get("name") or ""
    availability = str(offers.get("availability") or "").split("/")[-1]
    image = obj.get("image") or ""
    if isinstance(image, list):
        image = image[0] if image else ""
    return price, old, str(seller or ""), availability, str(image or ""), cur


async def _inspect(url: str, title: str, snippet: str) -> ProductResult:
    result = ProductResult(
        source=_source_for_url(url),
        title=title,
        url=url,
        match_hint=snippet[:220],
    )
    # برای اینستاگرام معمولاً قیمت مستقیم در صفحه عمومی نیست؛ فقط لینک و عنوان نگه می‌داریم
    if result.source == "instagram":
        result.seller = "صفحه اینستاگرامی"
        return result

    try:
        async with httpx.AsyncClient(
            timeout=14, follow_redirects=True, headers={"User-Agent": UA}
        ) as client:
            r = await client.get(url)
            if r.status_code >= 400:
                return result
        soup = BeautifulSoup(r.text, "html.parser")

        # JSON-LD اول
        for obj in _extract_jsonld(soup):
            typ = obj.get("@type")
            if typ == "Product" or (isinstance(typ, list) and "Product" in typ):
                p, old, seller, avail, image, cur = _from_product(obj)
                if p is not None:
                    result.price = p
                if old is not None and (result.price is None or old > result.price):
                    result.old_price = old
                result.seller = seller or result.seller
                result.availability = avail
                result.image = image
                result.currency = cur
                if result.price is not None:
                    break

        # Meta tags
        if result.price is None:
            meta = soup.select_one(
                'meta[property="product:price:amount"], meta[itemprop="price"], '
                'meta[property="og:price:amount"]'
            )
            if meta:
                result.price, result.currency = _currency_and_price(
                    meta.get("content") or meta.get("value"),
                    meta.get("contentCurrency", "") or "تومان",
                )

        # الگوهای متنی فارسی
        if result.price is None:
            text = soup.get_text(" ", strip=True)
            patterns = [
                r"([0-9۰-۹][0-9۰-۹,٬\.]{2,})\s*(?:تومان|تومن|ت\.?م)",
                r"(?:قیمت|Price|قیمت نهایی|قیمت فروش)\s*[:：]?\s*([0-9۰-۹][0-9۰-۹,٬\.]{2,})",
                r"([0-9۰-۹]{1,3}(?:[٬,][0-9۰-۹]{3})+)\s*(?:تومان|تومن)",
            ]
            for pat in patterns:
                m = re.search(pat, text, re.I)
                if m:
                    result.price, result.currency = _currency_and_price(m.group(1), "تومان")
                    break

        # عنوان بهتر از og:title
        og_title = soup.select_one('meta[property="og:title"]')
        if og_title and og_title.get("content"):
            clean = _clean_title(og_title["content"])
            if len(clean) > 8:
                result.title = clean

    except Exception as exc:
        logger.debug("shopping inspect failed %s: %s", url, exc)
    return result


def _query_variants(query: str) -> list[str]:
    """ساخت چند جستجوی کوتاه‌تر تا نتیجه به تطابق لفظ‌به‌لفظ وابسته نباشد."""
    q = re.sub(r"\s+", " ", (query or "").strip())
    if not q:
        return []

    variants: list[str] = [q]
    # کلمات کم‌ارزش در توصیف‌های بینایی را حذف می‌کنیم.
    stop = {
        "یک", "عدد", "نوع", "مدل", "شکل", "طرح", "دارای", "با", "و", "از",
        "برای", "در", "روی", "رنگ", "مناسب", "دکوری", "دکوراتیو", "خاص",
        "برجستگی", "برجسته", "تصویر", "عکس",
    }
    words = [w for w in re.findall(r"[\wآ-ی]{2,}", q.lower()) if w not in stop]
    if words:
        variants.append(" ".join(words))
    if len(words) >= 4:
        # دو نسخه کوتاه برای موتور جستجو؛ یکی ابتدای توصیف و یکی انتهای آن.
        variants.append(" ".join(words[:4]))
        variants.append(" ".join(words[-4:]))
    # چند جایگزین رایج برای توصیف‌های فارسی/بازاری.
    synonym_groups = [
        ("چوب پنبه ای", "چوب پنبه"),
        ("چوب‌پنبه‌ای", "چوب پنبه"),
        ("چوبی", "درب چوبی"),
        ("شیشه ای", "شیشه"),
        ("شیشه‌ای", "شیشه"),
    ]
    for a, b in synonym_groups:
        if a in q.lower():
            variants.append(q.lower().replace(a, b))

    out: list[str] = []
    seen: set[str] = set()
    for v in variants:
        v = re.sub(r"\s+", " ", v).strip()
        if len(v) >= 4 and v not in seen:
            seen.add(v)
            out.append(v)
    return out[:6]


def _score(result: ProductResult, query: str | list[str]) -> float:
    """امتیاز نرم؛ نتیجه مشابه را حذف نمی‌کند و بهترین query را ملاک می‌گیرد."""
    queries = query if isinstance(query, list) else _query_variants(query)
    if not queries:
        queries = [str(query or "")]

    text = f"{result.title} {result.match_hint}".lower()
    twords = {x.lower() for x in re.findall(r"[\wآ-ی]{2,}", text)}
    best = 0.0
    for q in queries:
        qwords = {x.lower() for x in re.findall(r"[\wآ-ی]{2,}", q)}
        if not qwords:
            continue
        overlap = len(qwords & twords) / max(1, len(qwords))
        # تطابق عبارت کامل امتیاز زیادی می‌گیرد، اما شرط نیست.
        phrase_bonus = 18 if q.lower() in text else 0
        best = max(best, overlap * 100 + phrase_bonus)

    score = best
    if result.price is not None:
        score += 12
    if result.seller:
        score += 3
    if result.source == "instagram":
        score += 4
    if result.source in ("torob", "digikala", "emalls"):
        score += 6
    return score


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
            key = hashlib.sha1(
                re.sub(r"\s+", " ", x.title.lower()).encode("utf-8", "ignore")
            ).hexdigest()[:24]
            c.execute(
                "INSERT INTO shopping_price_history(product_key,title,source,url,price) VALUES(?,?,?,?,?)",
                (key, x.title[:220], x.source, x.url[:1000], int(x.price)),
            )
        conn.commit()
        conn.close()
    except Exception as exc:
        logger.debug("shopping history save failed: %s", exc)


def shopping_price_history(query: str = "", days: int = 30, user_id: int = 0) -> str:
    query = (query or "").strip()
    if not query:
        return "نام محصول برای تاریخچه قیمت مشخص نیست."
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
        words = [w for w in re.findall(r"[\wآ-ی]{3,}", query.lower())][:8]
        rows = c.execute(
            "SELECT title,source,price,captured_at,url FROM shopping_price_history ORDER BY id DESC LIMIT 1200"
        ).fetchall()
        conn.close()
        matched = []
        for row in rows:
            title = str(row[0] or "").lower()
            if not words or sum(w in title for w in words) >= max(1, len(words) // 2):
                matched.append(row)
        if not matched:
            return "برای این محصول هنوز تاریخچه قیمتی از جستجوهای قبلی ربات ثبت نشده است."
        prices = [int(r[2]) for r in matched if r[2] is not None]
        lines = [
            f"📈 تاریخچه مشاهده‌شده قیمت برای «{query}»",
            f"تعداد مشاهدات: {len(prices)}",
        ]
        if prices:
            lines.append(
                f"کمترین: {min(prices):,} تومان | بیشترین: {max(prices):,} تومان | میانگین: {sum(prices)/len(prices):,.0f} تومان"
            )
        for r in matched[:12]:
            src = SOURCES.get(r[1], SOURCES["general"])["label"]
            lines.append(f"• {r[3]} | {src} | {int(r[2]):,} تومان")
        return "\n".join(lines)
    except Exception as exc:
        return f"تاریخچه قیمت در دسترس نیست: {exc}"


async def search_shopping(
    query: str = "",
    source: str = "all",
    max_results: int = 10,
    min_price: int = 0,
    max_price: int = 0,
    user_id: int = 0,
) -> str:
    """جستجوی هوشمند و گسترده قیمت محصول در فروشگاه‌های ایرانی + اینستاگرام + کل وب."""
    query = (query or "").strip()
    if not query:
        return "عبارت محصول برای جستجو مشخص نیست."

    max_results = max(4, min(int(max_results or 10), 14))
    source = (source or "all").lower().strip()

    # انتخاب منابع
    if source in ("all", "همه", "تمام", "everywhere", "web"):
        selected = list(SOURCES.keys())
    else:
        selected = [s for s in source.replace(",", " ").split() if s in SOURCES]
        if not selected:
            selected = list(SOURCES.keys())
    if "general" not in selected:
        selected.append("general")
    if "instagram" not in selected:
        selected.append("instagram")

    # چند query مستقل می‌سازیم؛ تطابق دقیق دیگر شرط موفقیت نیست.
    variants = _query_variants(query) or [query]
    tasks = []
    for key in selected:
        cfg = SOURCES[key]
        domain = cfg["domains"][0] if cfg["domains"] else ""
        limit = max(5, max_results // max(1, len(selected)) + 3)

        # برای هر منبع فقط چند query قوی‌تر را اجرا می‌کنیم تا روی Render فشار ایجاد نشود.
        local_variants = variants[:3] if key not in ("general", "instagram") else variants[:5]
        for variant in local_variants:
            if key == "instagram":
                tasks.append(
                    _search(f"{variant} {' OR '.join(INSTA_KEYWORDS[:3])}",
                            domain="instagram.com", limit=limit + 1)
                )
            elif key == "general":
                tasks.append(_search(variant, domain="", limit=limit + 2))
            else:
                tasks.append(_search(variant, domain=domain, limit=limit))

    batches = await asyncio.gather(*tasks, return_exceptions=True)

    # جمع‌آوری لینک‌های یکتا
    links: dict[str, dict[str, str]] = {}
    for batch in batches:
        if isinstance(batch, Exception):
            continue
        for item in batch:
            url = (item.get("url") or "").strip()
            if not url or url in links:
                continue
            # فیلتر لینک‌های بی‌ربط رایج
            low = url.lower()
            if any(
                x in low
                for x in (
                    "youtube.com",
                    "youtu.be",
                    "twitter.com",
                    "x.com",
                    "facebook.com",
                    "t.me/",
                    "telegram.",
                    "wikipedia.org",
                    "aparat.com",
                )
            ):
                continue
            links[url] = item

    # بازرسی صفحات (حداکثر ۲۶ تا برای سرعت)
    to_inspect = list(links.values())[:14]
    inspect_tasks = [
        _inspect(x["url"], x["title"], x.get("snippet", "")) for x in to_inspect
    ]
    results = await asyncio.gather(*inspect_tasks, return_exceptions=True)

    clean: list[ProductResult] = []
    for x in results:
        if not isinstance(x, ProductResult):
            continue
        if min_price and (x.price is None or x.price < min_price):
            continue
        if max_price and x.price is not None and x.price > max_price:
            continue
        clean.append(x)

    clean.sort(key=lambda x: (-_score(x, variants), x.price is None, x.price or 10**18))
    clean = clean[:max_results]
    _save_history(clean)

    if not clean:
        # fallback به لینک‌های خام
        fallback = list(links.values())[:max_results]
        if not fallback:
            return f"برای «{query}» نتیجه‌ای در فروشگاه‌ها، اینستاگرام و وب پیدا نشد."
        lines = [
            f"🔎 نتایج جستجو برای «{query}» (قیمت مستقیم استخراج نشد):",
            "لینک‌های مرتبط از فروشگاه‌ها و اینستاگرام:",
        ]
        for i, x in enumerate(fallback, 1):
            src = _source_for_url(x["url"])
            label = SOURCES.get(src, SOURCES["general"])["label"]
            lines.append(f"\n{i}. {x['title']}\n🏪 {label}\n🔗 {x['url']}")
        return "\n".join(lines)

    # ساخت خروجی نهایی
    lines = [
        f"🛒 **نتیجه جستجوی گسترده برای «{query}»**",
        "",
        "جستجو در فروشگاه‌های ایرانی + اینستاگرام + کل وب انجام شد.",
        "قیمت‌ها از صفحات در لحظه استخراج شده‌اند؛ قبل از خرید موجودی و قیمت نهایی را چک کنید.",
        "",
    ]

    for i, x in enumerate(clean, 1):
        source_label = SOURCES.get(x.source, SOURCES["general"])["label"]
        if x.price is not None:
            price = f"{x.price:,} تومان"
        else:
            price = "قیمت در صفحه مشخص نشد" if x.source != "instagram" else "قیمت در اینستا (معمولاً در پست/دایرکت)"

        extra = []
        if x.old_price and x.old_price > (x.price or 0):
            extra.append(f"قبلی: {x.old_price:,}")
        if x.seller:
            extra.append(f"فروشنده: {x.seller}")
        if x.availability:
            extra.append(f"وضعیت: {x.availability}")

        lines.append(f"{i}. **{x.title}**")
        lines.append(f"🏪 {source_label} | 💰 {price}")
        if extra:
            lines.append(" · ".join(extra))
        lines.append(f"🔗 {x.url}")
        lines.append("")

    # ارزان‌ترین (فقط بین آن‌هایی که قیمت دارند)
    priced = [x for x in clean if x.price is not None]
    if priced:
        cheapest = min(priced, key=lambda x: x.price or 10**18)
        lines.append(
            f"🏆 ارزان‌ترین نتیجه پیدا‌شده: **{cheapest.price:,} تومان** — "
            f"{SOURCES.get(cheapest.source, SOURCES['general'])['label']}"
        )

    # آمار منابع
    sources_count: dict[str, int] = {}
    for x in clean:
        sources_count[x.source] = sources_count.get(x.source, 0) + 1
    if sources_count:
        src_summary = " · ".join(
            f"{SOURCES.get(k, SOURCES['general'])['label']}: {v}"
            for k, v in sorted(sources_count.items(), key=lambda i: -i[1])
        )
        lines.append(f"\n📊 منابع: {src_summary}")

    return "\n".join(lines)

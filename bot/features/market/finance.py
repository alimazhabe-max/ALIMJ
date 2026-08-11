"""
مالی و بازار — ارز، فلزات، سکه (بدون کریپتو در قیمت اصلی)
کریپتو جدا + تبدیل سریع + سود/ضرر حرفه‌ای
"""
import re
import asyncio
from datetime import datetime
import httpx
from bs4 import BeautifulSoup
from bot.config import config
from bot.logger import logger

_cache = {}
_cache_t = {}
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0"}

# اسلاگ‌های TGJU (کلید داخلی → کلید ajax.json)
TGJU_SLUGS = {
    "dollar": "price_dollar_rl",
    "euro": "price_eur",
    "pound": "price_gbp",
    "dirham": "price_aed",
    "lira": "price_try",
    "yuan": "price_cny",
    "ruble": "price_rub",
    "afghani": "price_afn",
    "dinar_iq": "price_iqd",
    "gold18": "geram18",
    "silver": "silver_999",  # نقره ۹۹۹ به ریال
    "copper": "copper",
    "coin_emami": "sekee",
    "coin_bahar": "sekeb",
    "coin_half": "nim",
    "coin_quarter": "rob",
}

# یک درخواست برای همه قیمت‌ها
_AJAX_URLS = (
    "https://call1.tgju.org/ajax.json",
    "https://call2.tgju.org/ajax.json",
)
_BULK_CACHE_KEY = "tgju_bulk"
_BULK_TTL = 90  # ثانیه

SYMBOL_TO_ID = {
    "btc": "bitcoin", "bitcoin": "bitcoin", "بیتکوین": "bitcoin", "بیت‌کوین": "bitcoin",
    "eth": "ethereum", "ethereum": "ethereum", "اتریوم": "ethereum",
    "usdt": "tether", "tether": "tether", "تتر": "tether",
    "ton": "the-open-network", "toncoin": "the-open-network", "تون": "the-open-network",
    "bnb": "binancecoin", "sol": "solana", "xrp": "ripple", "ada": "cardano",
    "doge": "dogecoin", "dot": "polkadot", "matic": "matic-network", "avax": "avalanche-2",
    "link": "chainlink", "trx": "tron", "shib": "shiba-inu", "ltc": "litecoin",
}


def pn(n):
    return str(n).translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))


def _parse_price(raw) -> int | None:
    """تبدیل رشته قیمت TGJU به عدد صحیح (ریال)"""
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return int(raw)
    text = str(raw).replace(",", "").replace("٬", "").replace(" ", "").strip()
    if not text:
        return None
    try:
        return int(float(text))
    except Exception:
        return None


async def _fetch_tgju_bulk() -> dict:
    """یک درخواست JSON برای همه قیمت‌ها — خیلی سریع"""
    now = datetime.now().timestamp()
    if _BULK_CACHE_KEY in _cache and now - _cache_t.get(_BULK_CACHE_KEY, 0) < _BULK_TTL:
        return _cache[_BULK_CACHE_KEY]

    current = {}
    async with httpx.AsyncClient(timeout=8.0, headers=HEADERS, follow_redirects=True) as client:
        for url in _AJAX_URLS:
            try:
                r = await client.get(url)
                if r.status_code == 200:
                    data = r.json() or {}
                    current = data.get("current") or {}
                    if current:
                        break
            except Exception as e:
                logger.warning(f"tgju ajax {url}: {e}")

    if current:
        _cache[_BULK_CACHE_KEY] = current
        _cache_t[_BULK_CACHE_KEY] = now
    return current


async def _tgju_price(slug: str):
    """قیمت یک اسلاگ از کش bulk (بدون اسکرپ صفحه جدا)"""
    key = f"tgju_{slug}"
    now = datetime.now().timestamp()
    if key in _cache and now - _cache_t.get(key, 0) < _BULK_TTL:
        return _cache[key]

    bulk = await _fetch_tgju_bulk()
    item = bulk.get(slug)
    if isinstance(item, dict):
        val = _parse_price(item.get("p"))
    else:
        val = _parse_price(item)

    if val is not None:
        _cache[key] = val
        _cache_t[key] = now
        return val

    # fallback قدیمی: فقط برای یک اسلاگ اگر bulk نبود
    try:
        url = f"https://www.tgju.org/profile/{slug}"
        async with httpx.AsyncClient(timeout=5.0, headers=HEADERS, follow_redirects=True) as c:
            r = await c.get(url)
            r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        tag = soup.find(attrs={"data-col": "info.last_trade.PDrCotVal"})
        if tag:
            val = _parse_price(tag.get_text(strip=True))
            if val:
                _cache[key] = val
                _cache_t[key] = now
                return val
    except Exception as e:
        logger.error(f"tgju fallback {slug}: {e}")
    return None


async def _get_usd_rial():
    return await _tgju_price("price_dollar_rl")




async def _crypto_simple(ids: list):
    key = "cg_" + ",".join(sorted(ids))
    now = datetime.now().timestamp()
    if key in _cache and now - _cache_t.get(key, 0) < 60:
        return _cache[key]
    headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
    # CoinGecko
    try:
        async with httpx.AsyncClient(timeout=12.0, headers=headers) as client:
            r = await client.get(
                "https://api.coingecko.com/api/v3/simple/price",
                params={"ids": ",".join(ids), "vs_currencies": "usd"},
            )
            if r.status_code == 200:
                data = r.json()
                _cache[key] = data
                _cache_t[key] = now
                return data
    except Exception as e:
        logger.error(f"coingecko simple: {e}")
    # CoinPaprika fallback for known ids
    mapping = {
        "bitcoin": "btc-bitcoin", "ethereum": "eth-ethereum", "tether": "usdt-tether",
        "binancecoin": "bnb-binance-coin", "solana": "sol-solana", "ripple": "xrp-xrp",
        "the-open-network": "ton-toncoin", "dogecoin": "doge-dogecoin", "cardano": "ada-cardano",
        "tron": "trx-tron", "chainlink": "link-chainlink", "litecoin": "ltc-litecoin",
    }
    out = {}
    try:
        async with httpx.AsyncClient(timeout=12.0, headers=headers) as client:
            for cid in ids:
                pid = mapping.get(cid)
                if not pid:
                    continue
                r = await client.get(f"https://api.coinpaprika.com/v1/tickers/{pid}")
                if r.status_code == 200:
                    price = r.json().get("quotes", {}).get("USD", {}).get("price")
                    if price:
                        out[cid] = {"usd": float(price)}
        if out:
            _cache[key] = out
            _cache_t[key] = now
            return out
    except Exception as e:
        logger.error(f"paprika simple: {e}")
    return {}


async def _top_from_coinlore(limit: int = 20):
    try:
        async with httpx.AsyncClient(timeout=12.0, headers={"User-Agent": "Mozilla/5.0"}) as client:
            r = await client.get(f"https://api.coinlore.net/api/tickers/?start=0&limit={limit}")
            if r.status_code != 200:
                return []
            data = (r.json() or {}).get("data") or []
            out = []
            for row in data:
                out.append({
                    "symbol": (row.get("symbol") or "").upper(),
                    "price": float(row.get("price_usd") or 0),
                    "chg": float(row.get("percent_change_24h") or 0),
                })
            return out
    except Exception as e:
        logger.error(f"coinlore: {e}")
        return []


async def _top_from_paprika(limit: int = 20):
    try:
        async with httpx.AsyncClient(timeout=12.0, headers={"User-Agent": "Mozilla/5.0"}) as client:
            r = await client.get("https://api.coinpaprika.com/v1/tickers")
            if r.status_code != 200:
                return []
            data = r.json() or []
            # sort by rank
            data = sorted(data, key=lambda x: x.get("rank") or 9999)[:limit]
            out = []
            for row in data:
                q = (row.get("quotes") or {}).get("USD") or {}
                out.append({
                    "symbol": (row.get("symbol") or "").upper(),
                    "price": float(q.get("price") or 0),
                    "chg": float(q.get("percent_change_24h") or 0),
                })
            return out
    except Exception as e:
        logger.error(f"paprika top: {e}")
        return []


async def get_top_crypto(limit: int = 20) -> str:
    key = f"top_crypto_{limit}"
    now = datetime.now().timestamp()
    if key in _cache and now - _cache_t.get(key, 0) < 90:
        return _cache[key]

    usd_rial = await _get_usd_rial() or 0
    coins = []
    headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}

    # 1) CoinGecko
    try:
        async with httpx.AsyncClient(timeout=12.0, headers=headers) as client:
            r = await client.get(
                "https://api.coingecko.com/api/v3/coins/markets",
                params={
                    "vs_currency": "usd",
                    "order": "market_cap_desc",
                    "per_page": limit,
                    "page": 1,
                    "sparkline": "false",
                    "price_change_percentage": "24h",
                },
            )
            if r.status_code == 200:
                for coin in r.json():
                    coins.append({
                        "symbol": (coin.get("symbol") or "").upper(),
                        "price": coin.get("current_price") or 0,
                        "chg": coin.get("price_change_percentage_24h") or 0,
                    })
    except Exception as e:
        logger.error(f"coingecko markets: {e}")

    # 2) CoinLore
    if not coins:
        coins = await _top_from_coinlore(limit)

    # 3) CoinPaprika
    if not coins:
        coins = await _top_from_paprika(limit)

    if not coins:
        return "❌ لیست کریپتو موقتاً در دسترس نیست.\nکمی بعد دوباره امتحان کنید."

    lines = ["💎 ۲۰ ارز برتر کریپتو", "(دلار + تومان)", ""]
    for i, coin in enumerate(coins[:limit], 1):
        sym = coin.get("symbol") or "?"
        price = float(coin.get("price") or 0)
        chg = float(coin.get("chg") or 0)
        emoji = "🟢" if chg >= 0 else "🔴"
        toman = price * (usd_rial / 10) if usd_rial else 0
        p_str = f"${price:,.2f}" if price >= 1 else f"${price:.6f}"
        chg_str = f"{chg:+.1f}%" if chg else ""
        line = f"{pn(i)}. {sym} {emoji} {chg_str}".strip()
        line += f"\n   {p_str}"
        if toman:
            line += f"  ≈  {pn(f'{toman:,.0f}')} تومان"
        lines.append(line)

    result = "\n".join(lines)
    _cache[key] = result
    _cache_t[key] = now
    return result


async def convert_crypto(amount: float, symbol: str) -> str:
    symbol = symbol.lower().strip().replace(" ", "").replace("‌", "")
    coin_id = SYMBOL_TO_ID.get(symbol)
    if not coin_id:
        try:
            async with httpx.AsyncClient(timeout=6.0) as c:
                r = await c.get("https://api.coingecko.com/api/v3/search", params={"query": symbol})
                coins = r.json().get("coins", [])
                if coins:
                    coin_id = coins[0].get("id")
        except Exception:
            pass
    if not coin_id:
        return "❌ ارز پیدا نشد." + chr(10)*2 + "مثال: 20 ton یا 1.5 btc یا 100 usdt"
    prices = await _crypto_simple([coin_id])
    usd_price = prices.get(coin_id, {}).get("usd")
    if not usd_price:
        return "❌ قیمت این ارز در دسترس نیست."
    total_usd = amount * usd_price
    usd_rial = await _get_usd_rial() or 0
    total_toman = total_usd * (usd_rial / 10) if usd_rial else 0
    lines = [
        "🔄 مبدل ارز",
        "────────────────────",
        f"از: {pn(amount)} {symbol.upper()}",
        f"قیمت واحد: ${usd_price:,.6f}",
        "────────────────────",
        f"💵 دلار: ${total_usd:,.4f}",
        f"🇮🇷 تومان: {pn(f'{total_toman:,.0f}')}",
    ]
    if usd_rial:
        lines.append(f"📊 نرخ دلار: {pn(f'{usd_rial/10:,.0f}')} تومان")
    return chr(10).join(lines)


async def full_market_prices() -> str:
    """قیمت بازار بدون کریپتو — یک درخواست JSON (سریع)"""
    bulk = await _fetch_tgju_bulk()
    data = {}
    for key, slug in TGJU_SLUGS.items():
        item = bulk.get(slug)
        if isinstance(item, dict):
            data[key] = _parse_price(item.get("p"))
        else:
            data[key] = _parse_price(item)
        # fallback نقره اگر silver_999 نبود
        if key == "silver" and data[key] is None:
            alt = bulk.get("silver")
            if isinstance(alt, dict):
                # نقره جهانی دلاری — رد کن
                p = _parse_price(alt.get("p"))
                if p and p > 1000:
                    data[key] = p

    lines = ["💰 **قیمت بازار** (بدون کریپتو)\n"]

    def fmt(label, key, unit="ریال"):
        v = data.get(key)
        if v is None:
            return f"{label}: —"
        toman = v / 10
        return f"{label}: {pn(f'{v:,}')} {unit}  ({pn(f'{toman:,.0f}')} تومان)"

    lines.append("—— ارز ——")
    for label, key in [
        ("💵 دلار", "dollar"), ("💶 یورو", "euro"), ("💷 پوند", "pound"),
        ("🇦🇪 درهم", "dirham"), ("🇹🇷 لیر", "lira"),
        ("🇨🇳 یوان", "yuan"), ("🇷🇺 روبل", "ruble"),
        ("🇦🇫 افغانی", "afghani"), ("🇮🇶 دینار عراق", "dinar_iq"),
    ]:
        lines.append(fmt(label, key))

    lines.append("\n—— فلزات و سکه ——")
    for label, key in [
        ("🥇 طلای ۱۸", "gold18"), ("🥈 نقره ۹۹۹", "silver"), ("🟠 مس", "copper"),
        ("🪙 سکه امامی", "coin_emami"), ("🪙 سکه بهار", "coin_bahar"),
        ("🪙 نیم‌سکه", "coin_half"), ("🪙 ربع‌سکه", "coin_quarter"),
    ]:
        lines.append(fmt(label, key))

    lines.append("\n💡 کریپتو: از دکمه «۲۰ ارز برتر» یا تبدیل استفاده کنید.")
    return "\n".join(lines)


def rial_toman(amount: float, to_toman=True) -> str:
    if to_toman:
        return f"💵 {pn(f'{amount:,.0f}')} ریال = **{pn(f'{amount/10:,.0f}')} تومان**"
    return f"💵 {pn(f'{amount:,.0f}')} تومان = **{pn(f'{amount*10:,.0f}')} ریال**"


async def convert_currency(amount: float, from_cur: str, to_cur: str = "") -> str:
    """تبدیل ارز / کریپتو — ورودی انعطاف‌پذیر"""
    from_cur = (from_cur or "").lower().strip()
    to_cur = (to_cur or "").lower().strip()

    # اگر فقط یک نماد کریپتو
    if from_cur in SYMBOL_TO_ID or from_cur in ("btc", "eth", "ton", "usdt", "bnb", "sol"):
        return await convert_crypto(amount, from_cur)

    d = await _get_usd_rial()

    # ریال/تومان
    if from_cur in ("rial", "ریال", "irr") and to_cur in ("toman", "تومان", "tmn", ""):
        return rial_toman(amount, True)
    if from_cur in ("toman", "تومان", "tmn") and to_cur in ("rial", "ریال", "irr"):
        return rial_toman(amount, False)

    if d:
        if from_cur in ("usd", "دلار", "dollar") and to_cur in ("rial", "ریال", "toman", "تومان", ""):
            rial = amount * d
            return f"${amount:,.2f} = **{pn(f'{rial:,.0f}')} ریال** ({pn(f'{rial/10:,.0f}')} تومان)"
        if from_cur in ("toman", "تومان") and to_cur in ("usd", "دلار"):
            return f"{pn(f'{amount:,.0f}')} تومان = **${amount * 10 / d:,.2f}**"
        if from_cur in ("rial", "ریال") and to_cur in ("usd", "دلار"):
            return f"{pn(f'{amount:,.0f}')} ریال = **${amount / d:,.2f}**"

    # تلاش کریپتو با نام
    if re.match(r"^[a-zA-Z]{2,10}$", from_cur):
        return await convert_crypto(amount, from_cur)

    return (
        "❌ فرمت درست:\n"
        "• `100 دلار` یا `100 usd`\n"
        "• `50000 تومان دلار`\n"
        "• `20 ton` یا `1.5 btc`\n"
        "• `1000000 ریال تومان`"
    )


def profit_loss(buy: float, sell: float, qty: float = 1.0) -> str:
    """سود/ضرر حرفه‌ای با کارمزد اختیاری"""
    if buy <= 0:
        return "❌ قیمت خرید باید بزرگ‌تر از صفر باشد."
    gross = (sell - buy) * qty
    pct = (sell - buy) / buy * 100
    emoji = "📈" if gross >= 0 else "📉"
    status = "سود" if gross >= 0 else "ضرر"
    # پیشنهاد کارمزد تقریبی ۰.۵٪
    fee_est = (buy + sell) * qty * 0.005 / 2
    net = gross - fee_est
    return (
        f"{emoji} **محاسبه سود / ضرر**\n\n"
        f"قیمت خرید: {pn(f'{buy:,.0f}')}\n"
        f"قیمت فروش: {pn(f'{sell:,.0f}')}\n"
        f"تعداد / حجم: {pn(qty)}\n\n"
        f"**{status} ناخالص:** {pn(f'{abs(gross):,.0f}')}\n"
        f"**درصد:** {pct:+.2f}%\n"
        f"کارمزد تقریبی (۰.۵٪): {pn(f'{fee_est:,.0f}')}\n"
        f"**{status} تقریبی خالص:** {pn(f'{abs(net):,.0f}')}\n\n"
        f"{'✅ معامله در سود است.' if net >= 0 else '⚠️ معامله در ضرر است.'}"
    )


def parse_profit(text: str):
    t = text.translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789"))
    nums = re.findall(r"[\d]+(?:\.\d+)?", t)
    nums = [float(n) for n in nums]
    if len(nums) >= 2:
        return nums[0], nums[1], nums[2] if len(nums) > 2 else 1.0
    return None


def parse_currency_input(text: str):
    """پارس ورودی تبدیل: '20 ton' یا '100 دلار' یا '50 usdt تومان'"""
    t = text.strip().translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789"))
    t_lower = t.lower()
    m = re.match(r"([\d.]+)\s*([a-zA-Zآ-ی‌]+)?\s*([a-zA-Zآ-ی‌]+)?", t_lower)
    if not m:
        return None
    amount = float(m.group(1))
    a = (m.group(2) or "").strip()
    b = (m.group(3) or "").strip()
    return amount, a, b

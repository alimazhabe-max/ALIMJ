"""
مالی و بازار — ارز، فلزات، سکه + کریپتو کامل
نمودار قیمت + مبدل همه ارزهای دیجیتال + تحلیل چندمنبعی (CoinGecko + Binance + CoinPaprika + Fear&Greed + تلاش Coinglass)
"""
import re
import io
import asyncio
from datetime import datetime, timedelta
from typing import Optional, Tuple, List, Dict, Any
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
    "silver": "silver_999",
    "copper": "copper",
    "coin_emami": "sekee",
    "coin_bahar": "sekeb",
    "coin_half": "nim",
    "coin_quarter": "rob",
}

_AJAX_URLS = (
    "https://call1.tgju.org/ajax.json",
    "https://call2.tgju.org/ajax.json",
)
_BULK_CACHE_KEY = "tgju_bulk"
_BULK_TTL = 90

# نقشه نماد → شناسه CoinGecko (گسترده)
SYMBOL_TO_ID = {
    "btc": "bitcoin", "bitcoin": "bitcoin", "بیتکوین": "bitcoin", "بیت‌کوین": "bitcoin",
    "eth": "ethereum", "ethereum": "ethereum", "اتریوم": "ethereum",
    "usdt": "tether", "tether": "tether", "تتر": "tether",
    "usdc": "usd-coin", "busd": "binance-usd",
    "ton": "the-open-network", "toncoin": "the-open-network", "تون": "the-open-network",
    "bnb": "binancecoin", "sol": "solana", "xrp": "ripple", "ada": "cardano",
    "doge": "dogecoin", "dot": "polkadot", "matic": "matic-network", "polygon": "matic-network",
    "avax": "avalanche-2", "link": "chainlink", "trx": "tron", "shib": "shiba-inu",
    "ltc": "litecoin", "bch": "bitcoin-cash", "atom": "cosmos", "uni": "uniswap",
    "near": "near", "apt": "aptos", "arb": "arbitrum", "op": "optimism",
    "fil": "filecoin", "icp": "internet-computer", "vet": "vechain", "algo": "algorand",
    "xlm": "stellar", "eos": "eos", "xtz": "tezos", "aave": "aave",
    "mkr": "maker", "comp": "compound-governance-token", "snx": "havven",
    "crv": "curve-dao-token", "sushi": "sushi", "1inch": "1inch",
    "pepe": "pepe", "floki": "floki", "bonk": "bonk", "wif": "dogwifcoin",
    "sui": "sui", "sei": "sei-network", "inj": "injective-protocol",
    "tia": "celestia", "render": "render-token", "fet": "fetch-ai",
    "rndr": "render-token", "imx": "immutable-x", "gala": "gala",
    "sand": "the-sandbox", "mana": "decentraland", "axs": "axie-infinity",
    "theta": "theta-token", "ftm": "fantom", "hbar": "hedera-hashgraph",
    "egld": "elrond-erd-2", "kas": "kaspa", "rune": "thorchain",
    "stx": "blockstack", "ordi": "ordinals", "sats": "sats-ordinals",
}


def pn(n):
    return str(n).translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))


def _parse_price(raw) -> int | None:
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


async def resolve_coin_id(symbol: str) -> Optional[str]:
    """پیدا کردن شناسه CoinGecko از نماد یا نام — پشتیبانی تقریباً همه ارزها"""
    symbol = (symbol or "").lower().strip().replace(" ", "").replace("‌", "")
    if not symbol:
        return None
    if symbol in SYMBOL_TO_ID:
        return SYMBOL_TO_ID[symbol]

    cache_key = f"resolve_{symbol}"
    now = datetime.now().timestamp()
    if cache_key in _cache and now - _cache_t.get(cache_key, 0) < 3600:
        return _cache[cache_key]

    try:
        async with httpx.AsyncClient(timeout=8.0, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"}) as c:
            r = await c.get("https://api.coingecko.com/api/v3/search", params={"query": symbol})
            if r.status_code == 200:
                coins = r.json().get("coins") or []
                if coins:
                    for coin in coins:
                        if (coin.get("symbol") or "").lower() == symbol:
                            cid = coin.get("id")
                            _cache[cache_key] = cid
                            _cache_t[cache_key] = now
                            return cid
                    cid = coins[0].get("id")
                    _cache[cache_key] = cid
                    _cache_t[cache_key] = now
                    return cid
    except Exception as e:
        logger.warning(f"resolve_coin_id {symbol}: {e}")
    return None


async def _crypto_simple(ids: list):
    key = "cg_" + ",".join(sorted(ids))
    now = datetime.now().timestamp()
    if key in _cache and now - _cache_t.get(key, 0) < 60:
        return _cache[key]
    headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=12.0, headers=headers) as client:
            r = await client.get(
                "https://api.coingecko.com/api/v3/simple/price",
                params={
                    "ids": ",".join(ids),
                    "vs_currencies": "usd",
                    "include_24hr_change": "true",
                    "include_market_cap": "true",
                    "include_24hr_vol": "true",
                },
            )
            if r.status_code == 200:
                data = r.json()
                _cache[key] = data
                _cache_t[key] = now
                return data
    except Exception as e:
        logger.error(f"coingecko simple: {e}")

    mapping = {
        "bitcoin": "btc-bitcoin", "ethereum": "eth-ethereum", "tether": "usdt-tether",
        "binancecoin": "bnb-binance-coin", "solana": "sol-solana", "ripple": "xrp-xrp",
        "the-open-network": "ton-toncoin", "dogecoin": "doge-dogecoin", "cardano": "ada-cardano",
        "tron": "trx-tron", "chainlink": "link-chainlink", "litecoin": "ltc-litecoin",
        "polkadot": "dot-polkadot", "avalanche-2": "avax-avalanche", "shiba-inu": "shib-shiba-inu",
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


async def get_top_crypto(limit: int = 300) -> str:
    key = f"top_crypto_{limit}"
    now = datetime.now().timestamp()
    if key in _cache and now - _cache_t.get(key, 0) < 90:
        return _cache[key]

    usd_rial = await _get_usd_rial() or 0
    coins = []
    headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}

    try:
        async with httpx.AsyncClient(timeout=20.0, headers=headers) as client:
            pages = max(1, (min(limit, 300) + 249) // 250)
            for page in range(1, pages + 1):
                r = await client.get(
                    "https://api.coingecko.com/api/v3/coins/markets",
                    params={
                        "vs_currency": "usd",
                        "order": "market_cap_desc",
                        "per_page": min(250, limit - len(coins)),
                        "page": page,
                        "sparkline": "false",
                        "price_change_percentage": "24h",
                    },
                )
                if r.status_code != 200:
                    break
                batch = r.json() or []
                if not batch:
                    break
                for coin in batch:
                    coins.append({
                        "symbol": (coin.get("symbol") or "").upper(),
                        "price": coin.get("current_price") or 0,
                        "chg": coin.get("price_change_percentage_24h") or 0,
                    })
                if len(coins) >= limit:
                    break
    except Exception as e:
        logger.error(f"coingecko markets: {e}")

    if not coins:
        coins = await _top_from_coinlore(limit)
    if not coins:
        coins = await _top_from_paprika(limit)

    if not coins:
        return "❌ لیست کریپتو موقتاً در دسترس نیست.\nکمی بعد دوباره امتحان کنید."

    lines = [f"💎 {limit} ارز برتر کریپتو", "(دلار + تومان)", ""]
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
    """تبدیل هر ارز دیجیتال به دلار و تومان — پشتیبانی تقریباً همه کوین‌ها"""
    symbol = symbol.lower().strip().replace(" ", "").replace("‌", "")
    coin_id = await resolve_coin_id(symbol)
    if not coin_id:
        return (
            "❌ ارز پیدا نشد.\n\n"
            "مثال‌ها:\n"
            "• 1.5 btc\n"
            "• 20 ton\n"
            "• 100 pepe\n"
            "• 50 sol\n"
            "• 10 sui"
        )
    prices = await _crypto_simple([coin_id])
    info = prices.get(coin_id) or {}
    usd_price = info.get("usd")
    if not usd_price:
        return "❌ قیمت این ارز در دسترس نیست."
    total_usd = amount * usd_price
    usd_rial = await _get_usd_rial() or 0
    total_toman = total_usd * (usd_rial / 10) if usd_rial else 0
    chg = info.get("usd_24h_change")
    mcap = info.get("usd_market_cap")
    vol = info.get("usd_24h_vol")

    price_str = f"${usd_price:,.8f}" if usd_price < 1 else (f"${usd_price:,.4f}" if usd_price < 1000 else f"${usd_price:,.2f}")
    lines = [
        "🔄 مبدل ارز دیجیتال",
        "────────────────────",
        f"از: {pn(amount)} {symbol.upper()}",
        f"قیمت واحد: {price_str}",
    ]
    if chg is not None:
        emoji = "🟢" if chg >= 0 else "🔴"
        lines.append(f"تغییر ۲۴س: {emoji} {chg:+.2f}%")
    lines.append("────────────────────")
    lines.append(f"💵 دلار: ${total_usd:,.4f}")
    lines.append(f"🇮🇷 تومان: {pn(f'{total_toman:,.0f}')}")
    if usd_rial:
        lines.append(f"📊 نرخ دلار: {pn(f'{usd_rial/10:,.0f}')} تومان")
    if mcap:
        lines.append(f"🏛 مارکت‌کپ: ${mcap:,.0f}")
    if vol:
        lines.append(f"📈 حجم ۲۴س: ${vol:,.0f}")
    # معکوس تقریبی
    if amount and total_usd:
        lines.append("────────────────────")
        lines.append(f"🔁 ۱ دلار ≈ {pn(f'{1/usd_price:,.6f}')} {symbol.upper()}" if usd_price else "")
        if total_toman and amount:
            per_toman = amount / total_toman if total_toman else 0
            if per_toman:
                lines.append(f"🔁 ۱ میلیون تومان ≈ {pn(f'{per_toman * 1_000_000:,.6f}')} {symbol.upper()}")
    return "\n".join([x for x in lines if x])


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
        if key == "silver" and data[key] is None:
            alt = bulk.get("silver")
            if isinstance(alt, dict):
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

    lines.append("\n💡 کریپتو: از دکمه «۲۰ ارز برتر» یا تبدیل / نمودار / تحلیل استفاده کنید.")
    return "\n".join(lines)


def rial_toman(amount: float, to_toman=True) -> str:
    if to_toman:
        return f"💵 {pn(f'{amount:,.0f}')} ریال = **{pn(f'{amount/10:,.0f}')} تومان**"
    return f"💵 {pn(f'{amount:,.0f}')} تومان = **{pn(f'{amount*10:,.0f}')} ریال**"


# نام‌های رایج فارسی برای ارز و کریپتو
_FA_CURRENCY = {
    "دلار": "usd", "دلارآمریکا": "usd", "usd": "usd", "dollar": "usd", "دلاری": "usd",
    "یورو": "eur", "euro": "eur", "eur": "eur",
    "پوند": "gbp", "pound": "gbp", "gbp": "gbp",
    "تومان": "toman", "تومن": "toman", "tmn": "toman",
    "ریال": "rial", "irr": "rial",
    "درهم": "aed", "aed": "aed",
    "لیر": "try", "try": "try",
    "یوان": "cny", "cny": "cny",
    "روبل": "rub", "rub": "rub",
    "بیتکوین": "btc", "بیت‌کوین": "btc", "بیت کوین": "btc",
    "اتریوم": "eth", "تتر": "usdt", "تون": "ton", "سولانا": "sol",
    "کاردانو": "ada", "ریپل": "xrp", "دوج": "doge", "دوج‌کوین": "doge",
}


async def convert_currency(amount: float, from_cur: str, to_cur: str = "") -> str:
    """تبدیل ارز / کریپتو هوشمند — پشتیبانی گسترده + تبدیل دوطرفه"""
    from_cur = (from_cur or "").lower().strip().replace(" ", "").replace("‌", "")
    to_cur = (to_cur or "").lower().strip().replace(" ", "").replace("‌", "")

    from_cur = _FA_CURRENCY.get(from_cur, from_cur)
    to_cur = _FA_CURRENCY.get(to_cur, to_cur)

    # کریپتو → کریپتو یا کریپتو → فیات
    if from_cur in SYMBOL_TO_ID or re.match(r"^[a-zA-Z0-9]{2,15}$", from_cur):
        if to_cur and to_cur not in ("usd", "دلار", "toman", "تومان", "rial", "ریال", ""):
            id1 = await resolve_coin_id(from_cur)
            id2 = await resolve_coin_id(to_cur)
            if id1 and id2:
                prices = await _crypto_simple([id1, id2])
                p1 = prices.get(id1, {}).get("usd")
                p2 = prices.get(id2, {}).get("usd")
                if p1 and p2 and p2 > 0:
                    result = amount * p1 / p2
                    usd_rial = await _get_usd_rial() or 0
                    total_usd = amount * p1
                    total_toman = total_usd * (usd_rial / 10) if usd_rial else 0
                    return (
                        f"🔄 تبدیل کریپتو به کریپتو\n"
                        f"────────────────────\n"
                        f"{pn(amount)} {from_cur.upper()} = **{result:,.8f} {to_cur.upper()}**\n"
                        f"≈ ${total_usd:,.4f}\n"
                        + (f"≈ {pn(f'{total_toman:,.0f}')} تومان\n" if total_toman else "")
                        + f"────────────────────\n"
                        f"قیمت {from_cur.upper()}: ${p1:,.6f}\n"
                        f"قیمت {to_cur.upper()}: ${p2:,.6f}"
                    )
        return await convert_crypto(amount, from_cur)

    d = await _get_usd_rial()

    if from_cur in ("rial", "ریال", "irr") and to_cur in ("toman", "تومان", "tmn", ""):
        return rial_toman(amount, True)
    if from_cur in ("toman", "تومان", "tmn") and to_cur in ("rial", "ریال", "irr"):
        return rial_toman(amount, False)

    if d:
        if from_cur in ("usd",) and to_cur in ("rial", "toman", ""):
            rial = amount * d
            return (
                f"💵 تبدیل دلار\n"
                f"────────────────────\n"
                f"${amount:,.2f} = **{pn(f'{rial:,.0f}')} ریال**\n"
                f"≈ **{pn(f'{rial/10:,.0f}')} تومان**\n"
                f"نرخ: {pn(f'{d/10:,.0f}')} تومان"
            )
        if from_cur in ("toman",) and to_cur in ("usd", "دلار", ""):
            usd = amount * 10 / d
            return (
                f"🇮🇷 تبدیل تومان → دلار\n"
                f"────────────────────\n"
                f"{pn(f'{amount:,.0f}')} تومان = **${usd:,.4f}**\n"
                f"نرخ: {pn(f'{d/10:,.0f}')} تومان"
            )
        if from_cur in ("rial",) and to_cur in ("usd",):
            return f"{pn(f'{amount:,.0f}')} ریال = **${amount / d:,.4f}**"

    # اگر from کریپتو-like بود
    if re.match(r"^[a-zA-Z]{2,15}$", from_cur):
        return await convert_crypto(amount, from_cur)

    return (
        "❌ فرمت درست:\n"
        "• `100 دلار` یا `100 usd`\n"
        "• `50000 تومان دلار`\n"
        "• `20 ton` یا `1.5 btc` یا `100 pepe`\n"
        "• `1 btc eth` (تبدیل بین دو کریپتو)\n"
        "• `1000000 ریال تومان`\n"
        "• `50 تتر` یا `۲ بیتکوین`"
    )


def profit_loss(buy: float, sell: float, qty: float = 1.0) -> str:
    if buy <= 0:
        return "❌ قیمت خرید باید بزرگ‌تر از صفر باشد."
    gross = (sell - buy) * qty
    pct = (sell - buy) / buy * 100
    emoji = "📈" if gross >= 0 else "📉"
    status = "سود" if gross >= 0 else "ضرر"
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
    """پارس هوشمند: عدد + ارز مبدا + ارز مقصد (فارسی/انگلیسی)"""
    if not text:
        return None
    t = text.strip().translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789"))
    t = t.replace("،", "").replace(",", "")
    t_lower = t.lower().replace("‌", " ").replace("  ", " ").strip()

    # الگوهای رایج
    # 1) 20 ton / 1.5 btc usdt / 100 دلار تومان
    m = re.match(
        r"^([\d.]+)\s*([a-zA-Zآ-ی]+)?\s*(?:به|to|=|→|->)?\s*([a-zA-Zآ-ی]+)?\s*$",
        t_lower,
    )
    if m:
        amount = float(m.group(1))
        a = (m.group(2) or "").strip()
        b = (m.group(3) or "").strip()
        # نرمال‌سازی فارسی
        a = _FA_CURRENCY.get(a, a)
        b = _FA_CURRENCY.get(b, b)
        return amount, a, b

    # 2) فقط عدد و یک کلمه چسبیده: 100دلار
    m2 = re.match(r"^([\d.]+)\s*([a-zA-Zآ-ی]+)\s*$", t_lower)
    if m2:
        amount = float(m2.group(1))
        a = _FA_CURRENCY.get(m2.group(2).strip(), m2.group(2).strip())
        return amount, a, ""

    return None


# ─────────────────────────────────────────────────────────────────────────────
# نمودار قیمت کریپتو (باگ‌فیکس‌شده)
# ─────────────────────────────────────────────────────────────────────────────

async def get_crypto_chart(symbol: str, days: int = 7) -> Tuple[Optional[bytes], str]:
    """
    نمودار چندپنلی شبیه TradingView/AlgoAnalyzer:
    کندل + Bollinger + EMA + حجم + ADX + RSI
    """
    try:
        days = max(1, min(int(days or 7), 365))
    except Exception:
        days = 7

    symbol_clean = (symbol or "").lower().strip().replace(" ", "").replace("‌", "")
    for junk in ("نمودار", "chart", "قیمت", "روز", "روزه", "price", "تحلیل"):
        symbol_clean = symbol_clean.replace(junk, "")
    symbol_clean = symbol_clean.replace("usdt", "").strip() or "btc"

    coin_id = await resolve_coin_id(symbol_clean)
    _sym_map = {
        "bitcoin": "BTC", "ethereum": "ETH", "tether": "USDT", "binancecoin": "BNB",
        "solana": "SOL", "ripple": "XRP", "the-open-network": "TON", "dogecoin": "DOGE",
        "cardano": "ADA", "tron": "TRX", "chainlink": "LINK", "litecoin": "LTC",
        "polkadot": "DOT", "avalanche-2": "AVAX", "shiba-inu": "SHIB",
        "matic-network": "MATIC", "near": "NEAR", "pepe": "PEPE", "sui": "SUI",
    }
    pair = symbol_clean.upper().replace("USDT", "").replace("-", "") + "USDT"
    if coin_id and coin_id in _sym_map:
        pair = _sym_map[coin_id] + "USDT"
    elif symbol_clean in _sym_map:
        pair = _sym_map[symbol_clean] + "USDT"

    # انتخاب interval بر اساس days
    if days <= 3:
        interval, limit = "15m", min(300, days * 96)
    elif days <= 14:
        interval, limit = "1h", min(400, days * 24)
    elif days <= 60:
        interval, limit = "4h", min(400, days * 6)
    else:
        interval, limit = "1d", min(400, days)

    klines = await _fetch_klines_interval(pair, interval, int(limit))
    if not klines or len(klines) < 20:
        return None, (
            f"❌ داده نموداری برای {pair} در دسترس نیست.\n"
            "مثال: btc ، eth ، sol ، ton"
        )

    try:
        import numpy as np
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.patches import Rectangle
        plt.rcParams["axes.unicode_minus"] = False
        plt.rcParams["font.family"] = "DejaVu Sans"
    except ImportError as e:
        return None, f"❌ کتابخانه رسم نصب نیست: {e}"

    opens = np.array([float(k[1]) for k in klines], dtype=float)
    highs = np.array([float(k[2]) for k in klines], dtype=float)
    lows = np.array([float(k[3]) for k in klines], dtype=float)
    closes = np.array([float(k[4]) for k in klines], dtype=float)
    vols = np.array([float(k[5]) for k in klines], dtype=float)
    n = len(closes)
    x = np.arange(n)

    def _ema(arr, period):
        out = np.zeros(len(arr), dtype=float)
        out[0] = arr[0]
        a = 2.0 / (period + 1)
        for i in range(1, len(arr)):
            out[i] = a * arr[i] + (1 - a) * out[i - 1]
        return out

    def _rsi_arr(c, period=14):
        out = np.full(len(c), np.nan)
        if len(c) <= period:
            return out
        diff = np.diff(c)
        gains = np.where(diff > 0, diff, 0.0)
        losses = np.where(diff < 0, -diff, 0.0)
        ag = gains[:period].mean()
        al = losses[:period].mean()
        out[period] = 100.0 if al == 0 else 100 - 100 / (1 + ag / al)
        for i in range(period, len(diff)):
            ag = (ag * (period - 1) + gains[i]) / period
            al = (al * (period - 1) + losses[i]) / period
            out[i + 1] = 100.0 if al == 0 else 100 - 100 / (1 + ag / al)
        return out

    def _adx_arr(h, l, c, period=14):
        out = np.full(len(c), np.nan)
        if len(c) < period + 2:
            return out
        tr = np.zeros(len(c))
        dp = np.zeros(len(c))
        dm = np.zeros(len(c))
        for i in range(1, len(c)):
            tr[i] = max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1]))
            up = h[i] - h[i - 1]
            dn = l[i - 1] - l[i]
            dp[i] = up if up > dn and up > 0 else 0
            dm[i] = dn if dn > up and dn > 0 else 0
        atr = tr.copy()
        for i in range(period, len(c)):
            atr[i] = atr[i - 1] - atr[i - 1] / period + tr[i] if i > period else tr[1:i + 1].mean()
        dxs = []
        for i in range(period, len(c)):
            atr_v = atr[i] if atr[i] else 1e-9
            di_p = 100 * (dp[i - period + 1:i + 1].mean()) / atr_v
            di_m = 100 * (dm[i - period + 1:i + 1].mean()) / atr_v
            s = di_p + di_m
            dx = 0 if s == 0 else 100 * abs(di_p - di_m) / s
            dxs.append(dx)
            out[i] = dx if len(dxs) < period else float(np.mean(dxs[-period:]))
        return out

    ema20 = _ema(closes, 20)
    ema50 = _ema(closes, 50) if n >= 50 else _ema(closes, max(10, n // 3))
    # Bollinger
    bb_period = 20
    sma = np.convolve(closes, np.ones(bb_period) / bb_period, mode="same")
    std = np.array([closes[max(0, i - bb_period + 1):i + 1].std() for i in range(n)])
    bb_u, bb_l = sma + 2 * std, sma - 2 * std
    rsi = _rsi_arr(closes, 14)
    adx = _adx_arr(highs, lows, closes, 14)

    try:
        fig = plt.figure(figsize=(11, 8.5), dpi=120)
        gs = fig.add_gridspec(4, 1, height_ratios=[3.2, 0.9, 0.9, 0.9], hspace=0.08)
        ax_price = fig.add_subplot(gs[0])
        ax_vol = fig.add_subplot(gs[1], sharex=ax_price)
        ax_adx = fig.add_subplot(gs[2], sharex=ax_price)
        ax_rsi = fig.add_subplot(gs[3], sharex=ax_price)

        # BB
        ax_price.fill_between(x, bb_l, bb_u, color="#93c5fd", alpha=0.35, label="BBANDS(20,2)")
        ax_price.plot(x, sma, color="#3b82f6", linewidth=0.9, linestyle="--", alpha=0.9)

        # Candles
        width = 0.55
        for i in range(n):
            color = "#16a34a" if closes[i] >= opens[i] else "#dc2626"
            ax_price.plot([i, i], [lows[i], highs[i]], color=color, linewidth=0.7, solid_capstyle="round")
            body = abs(closes[i] - opens[i])
            bottom = min(opens[i], closes[i])
            if body < (highs[i] - lows[i]) * 0.001:
                body = max((highs[i] - lows[i]) * 0.01, closes[i] * 0.00005)
            ax_price.add_patch(
                Rectangle((i - width / 2, bottom), width, body, facecolor=color, edgecolor=color, linewidth=0.4)
            )

        ax_price.plot(x, ema20, color="#0ea5e9", linewidth=1.2, label="EMA(20)")
        ax_price.plot(x, ema50, color="#f59e0b", linewidth=1.2, label="EMA(50)")
        ax_price.set_title(f"{pair} — {days}D Chart ({interval})", fontsize=12, fontweight="bold")
        ax_price.legend(loc="upper left", fontsize=8, framealpha=0.85)
        ax_price.grid(True, alpha=0.25, linestyle="--")
        ax_price.set_ylabel("USD")
        plt.setp(ax_price.get_xticklabels(), visible=False)

        # Volume
        vcolors = ["#16a34a" if closes[i] >= opens[i] else "#dc2626" for i in range(n)]
        ax_vol.bar(x, vols, color=vcolors, width=0.75, alpha=0.75)
        ax_vol.set_ylabel("Vol")
        ax_vol.grid(True, alpha=0.25)
        plt.setp(ax_vol.get_xticklabels(), visible=False)

        # ADX
        ax_adx.plot(x, adx, color="#111827", linewidth=1.1, label="ADX(14)")
        ax_adx.axhline(25, color="#9ca3af", linestyle="--", linewidth=0.7)
        ax_adx.set_ylabel("ADX")
        ax_adx.legend(loc="upper left", fontsize=7)
        ax_adx.grid(True, alpha=0.25)
        plt.setp(ax_adx.get_xticklabels(), visible=False)

        # RSI
        ax_rsi.plot(x, rsi, color="#111827", linewidth=1.1, label="RSI(14)")
        ax_rsi.axhline(70, color="#9ca3af", linestyle="--", linewidth=0.7)
        ax_rsi.axhline(30, color="#9ca3af", linestyle="--", linewidth=0.7)
        ax_rsi.set_ylim(0, 100)
        ax_rsi.set_ylabel("RSI")
        ax_rsi.legend(loc="upper left", fontsize=7)
        ax_rsi.grid(True, alpha=0.25)

        # x labels sparse
        step = max(1, n // 8)
        ticks = list(range(0, n, step))
        if n - 1 not in ticks:
            ticks.append(n - 1)
        labels = []
        for i in ticks:
            ts = int(klines[i][0])
            if ts < 1e12:
                ts *= 1000
            dt = datetime.utcfromtimestamp(ts / 1000.0)
            labels.append(dt.strftime("%m/%d" if days > 3 else "%m/%d %H"))
        ax_rsi.set_xticks(ticks)
        ax_rsi.set_xticklabels(labels, rotation=20, fontsize=8)

        fig.subplots_adjust(left=0.08, right=0.98, top=0.95, bottom=0.08)
        buf = io.BytesIO()
        fig.savefig(buf, format="png", facecolor="white")
        plt.close(fig)
        buf.seek(0)
        png = buf.read()
    except Exception as e:
        logger.error(f"chart draw: {e}")
        try:
            plt.close("all")
        except Exception:
            pass
        return None, f"❌ خطا در رسم نمودار: {e}"

    first, last = float(closes[0]), float(closes[-1])
    chg = ((last - first) / first * 100) if first else 0
    emoji = "🟢" if chg >= 0 else "🔴"
    caption = (
        f"📊 {pair} | {days}D ({interval})\n"
        f"Start: ${first:,.4f} → End: ${last:,.4f}\n"
        f"High/Low: ${float(highs.max()):,.4f} / ${float(lows.min()):,.4f}\n"
        f"Change: {emoji} {chg:+.2f}%\n"
        f"EMA20/50 + BB + Vol + ADX + RSI"
    )
    return png, caption


async def _fetch_klines_interval(pair: str, interval: str, limit: int) -> list:
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        async with httpx.AsyncClient(timeout=18.0, headers=headers) as c:
            r = await c.get(
                "https://data-api.binance.vision/api/v3/klines",
                params={"symbol": pair, "interval": interval, "limit": limit},
            )
            if r.status_code == 200:
                data = r.json() or []
                if data:
                    return data
            # OKX map
            okx_bar = {"15m": "15m", "1h": "1H", "4h": "4H", "1d": "1D"}.get(interval, "1H")
            okx_sym = pair.replace("USDT", "-USDT")
            r2 = await c.get(
                "https://www.okx.com/api/v5/market/candles",
                params={"instId": okx_sym, "bar": okx_bar, "limit": str(min(limit, 300))},
            )
            if r2.status_code == 200:
                rows = (r2.json() or {}).get("data") or []
                out = []
                for row in reversed(rows):
                    out.append([int(row[0]), row[1], row[2], row[3], row[4], row[5]])
                return out
    except Exception as e:
        logger.warning(f"klines interval: {e}")
    return []



async def _fetch_coingecko_detail(coin_id: str) -> dict:
    try:
        async with httpx.AsyncClient(timeout=12.0, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"}) as c:
            r = await c.get(
                f"https://api.coingecko.com/api/v3/coins/{coin_id}",
                params={
                    "localization": "false",
                    "tickers": "false",
                    "market_data": "true",
                    "community_data": "false",
                    "developer_data": "false",
                },
            )
            if r.status_code == 200:
                return r.json() or {}
    except Exception as e:
        logger.warning(f"cg detail: {e}")
    return {}


async def _fetch_binance_futures(symbol: str) -> dict:
    sym = (symbol or "").upper().replace("USDT", "") + "USDT"
    out = {}
    try:
        async with httpx.AsyncClient(timeout=10.0) as c:
            r = await c.get("https://fapi.binance.com/fapi/v1/premiumIndex", params={"symbol": sym})
            if r.status_code == 200:
                d = r.json()
                out["funding_rate"] = float(d.get("lastFundingRate") or 0) * 100
                out["mark_price"] = float(d.get("markPrice") or 0)
            r2 = await c.get("https://fapi.binance.com/fapi/v1/openInterest", params={"symbol": sym})
            if r2.status_code == 200:
                out["open_interest"] = float(r2.json().get("openInterest") or 0)
            r3 = await c.get("https://fapi.binance.com/fapi/v1/ticker/24hr", params={"symbol": sym})
            if r3.status_code == 200:
                tk = r3.json()
                out["volume_24h"] = float(tk.get("quoteVolume") or 0)
                out["price_change_pct"] = float(tk.get("priceChangePercent") or 0)
    except Exception as e:
        logger.warning(f"binance futures {sym}: {e}")
    return out


async def _fetch_fear_greed():
    try:
        async with httpx.AsyncClient(timeout=8.0) as c:
            r = await c.get("https://api.alternative.me/fng/?limit=1")
            if r.status_code == 200:
                data = (r.json() or {}).get("data") or []
                if data:
                    return data[0]
    except Exception as e:
        logger.warning(f"fear greed: {e}")
    return None


async def analyze_crypto(symbol: str, ai_summary: str = "") -> str:
    """
    خروجی یک‌تکه و حرفه‌ای شبیه ربات‌های تحلیل:
    خلاصه کلی + سیگنال + امتیاز + جمع‌بندی AI در همان پیام
    """
    symbol_clean = (symbol or "").lower().strip().replace(" ", "").replace("‌", "")
    for junk in ("تحلیل", "analyze", "ارز", "کریپتو"):
        if symbol_clean.startswith(junk):
            symbol_clean = symbol_clean[len(junk):].strip()
    symbol_clean = symbol_clean.replace("usdt", "").strip() or "btc"

    coin_id = await resolve_coin_id(symbol_clean)
    _sym_map = {
        "bitcoin": "BTC", "ethereum": "ETH", "tether": "USDT", "binancecoin": "BNB",
        "solana": "SOL", "ripple": "XRP", "the-open-network": "TON", "dogecoin": "DOGE",
        "cardano": "ADA", "tron": "TRX", "chainlink": "LINK", "litecoin": "LTC",
        "polkadot": "DOT", "avalanche-2": "AVAX", "shiba-inu": "SHIB",
        "matic-network": "MATIC", "near": "NEAR", "pepe": "PEPE", "sui": "SUI",
    }
    pair = symbol_clean.upper().replace("USDT", "").replace("-", "") + "USDT"
    if coin_id and coin_id in _sym_map:
        pair = _sym_map[coin_id] + "USDT"
    base = pair.replace("USDT", "")

    detail_t = _fetch_coingecko_detail(coin_id) if coin_id else _empty_detail()
    binance_t = _fetch_binance_futures(symbol_clean)
    fg_t = _fetch_fear_greed()
    klines_t = _fetch_klines_for_ta(pair, limit=200)

    detail, binance, fg, klines = await asyncio.gather(detail_t, binance_t, fg_t, klines_t)

    md = (detail.get("market_data") or {}) if isinstance(detail, dict) else {}
    current = md.get("current_price", {}).get("usd")
    mcap = md.get("market_cap", {}).get("usd")
    vol = md.get("total_volume", {}).get("usd")
    chg_1h = md.get("price_change_percentage_1h_in_currency", {}).get("usd")
    chg_24 = md.get("price_change_percentage_24h")
    chg_7d = md.get("price_change_percentage_7d")
    high_24 = md.get("high_24h", {}).get("usd")
    low_24 = md.get("low_24h", {}).get("usd")
    rank = detail.get("market_cap_rank") if isinstance(detail, dict) else None
    name = (detail.get("name") if isinstance(detail, dict) else None) or base

    closes, highs, lows, opens, vols = [], [], [], [], []
    if klines:
        for k in klines:
            try:
                opens.append(float(k[1])); highs.append(float(k[2]))
                lows.append(float(k[3])); closes.append(float(k[4])); vols.append(float(k[5]))
            except Exception:
                continue
    if current is None and closes:
        current = closes[-1]

    ta = _compute_ta(closes, highs, lows, vols) if len(closes) >= 30 else {}
    support, resistance = _support_resistance(closes, highs, lows, current)
    trend = ta.get("trend", "خنثی")
    trend_arrow = {"صعودی": "صعودی ↗️", "نزولی": "نزولی ↘️", "خنثی": "خنثی ↔️"}.get(trend, "خنثی ↔️")
    signal, signal_emoji, setup_score, rr_quality, risk_level, exec_status = _derive_signal(ta, chg_24, binance or {})

    # سیگنال فارسی مثل نمونه
    signal_fa = signal
    if "لانگ" in signal:
        signal_fa = f"لانگ {signal_emoji}"
    elif "شورت" in signal:
        signal_fa = f"شورت {signal_emoji}"
    else:
        signal_fa = f"{signal} {signal_emoji}"

    def fmt_p(v):
        if v is None:
            return "—"
        if v >= 1000:
            return f"{v:,.2f}"
        if v >= 1:
            return f"{v:,.4f}"
        return f"{v:,.6f}"

    # جمع‌بندی هوشمند محلی (اگر AI نداد)
    if not ai_summary:
        ai_summary = _build_smart_summary(
            pair, trend, ta, support, resistance, signal, setup_score, chg_24, binance or {}, current
        )

    lines = [
        f"▎1. 📰 خلاصه کلی — {pair}",
        f"🧭 روند: {trend_arrow}",
        f"🛡 حمایت کلیدی: {fmt_p(support)}",
        f"🧱 مقاومت کلیدی: {fmt_p(resistance)}",
        f"🎯 نوع سیگنال: {signal_fa}",
        f"⭐️ امتیاز کیفیت ستاپ: {setup_score}.0" if isinstance(setup_score, int) else f"⭐️ امتیاز کیفیت ستاپ: {setup_score}",
        f"⚖️ کیفیت ریوارد (R:R وزنی): {rr_quality}",
        f"⚠️ سطح ریسک (حد ضرر): {risk_level}",
        f"🔖 وضعیت اجرا: {exec_status}",
        f"📝 جمع‌بندی: {ai_summary}",
        "",
        "▎2. 💵 قیمت و بازار",
    ]
    if current is not None:
        lines.append(f"قیمت: ${fmt_p(current)}")
    if rank:
        lines.append(f"رتبه: #{rank}")
    if mcap:
        lines.append(f"مارکت‌کپ: ${mcap:,.0f}")
    if vol:
        lines.append(f"حجم ۲۴س: ${vol:,.0f}")
    bits = []
    for label, val in [("۱س", chg_1h), ("۲۴س", chg_24), ("۷ر", chg_7d)]:
        if val is not None:
            em = "🟢" if val >= 0 else "🔴"
            bits.append(f"{label} {em}{val:+.2f}%")
    if bits:
        lines.append("تغییرات: " + " | ".join(bits))
    if high_24 is not None and low_24 is not None:
        lines.append(f"سقف/کف ۲۴س: ${fmt_p(high_24)} / ${fmt_p(low_24)}")

    if ta:
        lines.append("")
        lines.append("▎3. 📊 اندیکاتورها")
        if ta.get("rsi") is not None:
            rsi = ta["rsi"]
            rsi_s = "اشباع خرید" if rsi >= 70 else ("اشباع فروش" if rsi <= 30 else "خنثی")
            lines.append(f"RSI(14): {rsi:.1f} — {rsi_s}")
        if ta.get("adx") is not None:
            lines.append(f"ADX(14): {ta['adx']:.1f} {'قوی' if ta['adx'] >= 25 else 'ضعیف'}")
        if ta.get("sma20") is not None:
            lines.append(f"SMA20: ${fmt_p(ta['sma20'])}")
        if ta.get("sma50") is not None:
            lines.append(f"SMA50: ${fmt_p(ta['sma50'])}")

    if binance:
        lines.append("")
        lines.append("▎4. 📉 فیوچرز")
        if "funding_rate" in binance:
            fr = binance["funding_rate"]
            lines.append(f"Funding: {fr:+.4f}%")
        if binance.get("open_interest"):
            lines.append(f"OI: {binance['open_interest']:,.0f}")

    if fg:
        lines.append("")
        lines.append(f"😱 Fear & Greed: {fg.get('value')} — {fg.get('value_classification')}")

    lines.append("")
    lines.append("⚠️ صرفاً تحلیلی/آموزشی است؛ توصیه سرمایه‌گذاری قطعی نیست.")
    return "\n".join(lines)


async def _empty_detail():
    return {}


def _build_smart_summary(pair, trend, ta, support, resistance, signal, score, chg_24, binance, current) -> str:
    """جمع‌بندی حرفه‌ای بدون نیاز به AI جدا"""
    parts = []
    if trend == "نزولی":
        parts.append("بازار در تایم‌فریم اخیر زیر میانگین‌های متحرک و با مومنتوم نزولی حرکت می‌کند.")
    elif trend == "صعودی":
        parts.append("بازار بالای میانگین‌های متحرک قرار دارد و مومنتوم کوتاه‌مدت صعودی است.")
    else:
        parts.append("بازار در وضعیت رنج/خنثی است و قدرت روند محدود به نظر می‌رسد.")

    rsi = ta.get("rsi")
    adx = ta.get("adx")
    if rsi is not None:
        if rsi >= 70:
            parts.append("RSI در ناحیه اشباع خرید است و احتمال اصلاح وجود دارد.")
        elif rsi <= 30:
            parts.append("RSI در ناحیه اشباع فروش است و احتمال برگشت کوتاه‌مدت مطرح است.")
        else:
            parts.append(f"RSI در محدوده میانی ({rsi:.0f}) قرار دارد.")

    if adx is not None:
        if adx >= 25:
            parts.append("ADX قدرت روند را تأیید می‌کند.")
        else:
            parts.append("ADX نشان‌دهنده روند ضعیف یا بازار رنج است.")

    if "شورت" in signal:
        parts.append("استراتژی محتمل: فروش در پولبک به سمت مقاومت‌های نزدیک.")
    elif "لانگ" in signal:
        parts.append("استراتژی محتمل: خرید در برگشت به حمایت‌های نزدیک.")
    else:
        parts.append("بهتر است تا شکست واضح حمایت/مقاومت صبر شود.")

    if support and resistance:
        parts.append(f"محدوده کلیدی حدود {support:,.0f} تا {resistance:,.0f} است." if support > 10 else f"محدوده کلیدی حدود {support:.4f} تا {resistance:.4f} است.")

    return " ".join(parts)


async def _fetch_klines_for_ta(pair: str, limit: int = 200) -> list:
    """OHLCV از Binance Vision برای تحلیل تکنیکال"""
    try:
        async with httpx.AsyncClient(timeout=15.0, headers={"User-Agent": "Mozilla/5.0"}) as c:
            r = await c.get(
                "https://data-api.binance.vision/api/v3/klines",
                params={"symbol": pair, "interval": "1h", "limit": limit},
            )
            if r.status_code == 200:
                return r.json() or []
            # OKX fallback
            okx = pair.replace("USDT", "-USDT")
            r2 = await c.get(
                "https://www.okx.com/api/v5/market/candles",
                params={"instId": okx, "bar": "1H", "limit": str(min(limit, 300))},
            )
            if r2.status_code == 200:
                data = (r2.json() or {}).get("data") or []
                # OKX newest first → reverse; map to binance-like
                out = []
                for row in reversed(data):
                    out.append([int(row[0]), row[1], row[2], row[3], row[4], row[5]])
                return out
    except Exception as e:
        logger.warning(f"klines ta: {e}")
    return []


def _sma(arr: list, n: int):
    if len(arr) < n:
        return None
    return sum(arr[-n:]) / n


def _rsi(closes: list, period: int = 14) -> float | None:
    if len(closes) < period + 1:
        return None
    gains, losses = [], []
    for i in range(-period, 0):
        d = closes[i] - closes[i - 1]
        gains.append(max(d, 0))
        losses.append(max(-d, 0))
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def _adx_approx(highs: list, lows: list, closes: list, period: int = 14) -> float | None:
    """تقریب ساده ADX"""
    if len(closes) < period * 2:
        return None
    trs = []
    dms_p, dms_m = [], []
    for i in range(1, len(closes)):
        tr = max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
        trs.append(tr)
        up = highs[i] - highs[i - 1]
        dn = lows[i - 1] - lows[i]
        dms_p.append(up if up > dn and up > 0 else 0)
        dms_m.append(dn if dn > up and dn > 0 else 0)
    if len(trs) < period:
        return None
    atr = sum(trs[-period:]) / period
    if atr == 0:
        return 0.0
    di_p = 100 * (sum(dms_p[-period:]) / period) / atr
    di_m = 100 * (sum(dms_m[-period:]) / period) / atr
    denom = di_p + di_m
    if denom == 0:
        return 0.0
    dx = 100 * abs(di_p - di_m) / denom
    return dx


def _compute_ta(closes, highs, lows, vols) -> dict:
    out = {}
    out["sma20"] = _sma(closes, 20)
    out["sma50"] = _sma(closes, 50) if len(closes) >= 50 else _sma(closes, 30)
    out["rsi"] = _rsi(closes, 14)
    out["adx"] = _adx_approx(highs, lows, closes, 14)
    if vols and len(vols) >= 20:
        avg_vol = sum(vols[-20:]) / 20
        out["vol_ratio"] = (vols[-1] / avg_vol) if avg_vol else 1.0
    # روند
    sma20, sma50 = out.get("sma20"), out.get("sma50")
    price = closes[-1]
    if sma20 and sma50:
        if price > sma20 > sma50:
            out["trend"] = "صعودی"
        elif price < sma20 < sma50:
            out["trend"] = "نزولی"
        else:
            out["trend"] = "خنثی"
    elif sma20:
        out["trend"] = "صعودی" if price > sma20 else "نزولی"
    else:
        out["trend"] = "خنثی"
    # شیب اخیر
    if len(closes) >= 24:
        chg = (closes[-1] - closes[-24]) / closes[-24] * 100
        out["chg_24h_bar"] = chg
        if out["trend"] == "خنثی":
            if chg > 2:
                out["trend"] = "صعودی"
            elif chg < -2:
                out["trend"] = "نزولی"
    return out


def _support_resistance(closes, highs, lows, current):
    if not closes:
        return None, None
    window = closes[-48:] if len(closes) >= 48 else closes
    hi_w = highs[-48:] if len(highs) >= 48 else highs
    lo_w = lows[-48:] if len(lows) >= 48 else lows
    resistance = max(hi_w) if hi_w else max(window)
    support = min(lo_w) if lo_w else min(window)
    # نزدیک‌تر کردن به قیمت فعلی با pivot ساده
    if current:
        # حمایت: بالاترین low زیر قیمت
        below = [x for x in lo_w if x < current * 0.999]
        above = [x for x in hi_w if x > current * 1.001]
        if below:
            support = max(below)
        if above:
            resistance = min(above)
    return support, resistance


def _derive_signal(ta: dict, chg_24, binance: dict):
    """سیگنال، امتیاز، R:R، ریسک، وضعیت اجرا"""
    trend = ta.get("trend", "خنثی")
    rsi = ta.get("rsi")
    adx = ta.get("adx") or 0
    score = 5
    signal = "خنثی"
    signal_emoji = "⚪"

    if trend == "صعودی":
        signal, signal_emoji = "لانگ", "🟢"
        score += 1
    elif trend == "نزولی":
        signal, signal_emoji = "شورت", "🔴"
        score += 1

    if rsi is not None:
        if signal == "لانگ" and rsi < 40:
            score += 2
        elif signal == "شورت" and rsi > 60:
            score += 2
        elif signal == "لانگ" and rsi > 70:
            score -= 2
            signal = "خنثی / احتیاط"
            signal_emoji = "🟡"
        elif signal == "شورت" and rsi < 30:
            score -= 2
            signal = "خنثی / احتیاط"
            signal_emoji = "🟡"

    if adx >= 25:
        score += 1
    elif adx < 15:
        score -= 1

    fr = (binance or {}).get("funding_rate")
    if fr is not None:
        if signal == "لانگ" and fr < 0:
            score += 1
        elif signal == "شورت" and fr > 0:
            score += 1
        elif signal == "لانگ" and fr > 0.03:
            score -= 1
        elif signal == "شورت" and fr < -0.03:
            score -= 1

    score = max(1, min(10, score))

    if score >= 8:
        rr = "خوب 🟢"
        risk = "متوسط 🟡"
        status = "قابل معامله ✅"
    elif score >= 5:
        rr = "متوسط 🟡"
        risk = "متوسط 🟡"
        status = "با احتیاط ⚠️"
    else:
        rr = "ضعیف 🔴"
        risk = "بالا 🔴"
        status = "صبر کنید ❌"

    return signal, signal_emoji, score, rr, risk, status


async def get_crypto_analysis_short(symbol: str) -> str:
    """نسخه کوتاه‌تر برای ابزار AI"""
    return await analyze_crypto(symbol)

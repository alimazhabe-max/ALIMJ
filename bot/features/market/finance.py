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


async def get_top_crypto(limit: int = 20) -> str:
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
        from matplotlib.patches import Rectangle, FancyBboxPatch
        from matplotlib.collections import LineCollection
        plt.rcParams.update({
            "axes.unicode_minus": False,
            "font.family": "DejaVu Sans",
            "figure.facecolor": "#0b0e11",
            "axes.facecolor": "#0b0e11",
            "savefig.facecolor": "#0b0e11",
            "text.color": "#e5e7eb",
            "axes.labelcolor": "#9ca3af",
            "xtick.color": "#9ca3af",
            "ytick.color": "#9ca3af",
            "axes.edgecolor": "#1f2937",
            "grid.color": "#1f2937",
            "grid.linestyle": "-",
            "grid.linewidth": 0.6,
            "grid.alpha": 0.9,
        })
    except ImportError as e:
        return None, f"❌ کتابخانه رسم نصب نیست: {e}"

    opens = np.array([float(k[1]) for k in klines], dtype=float)
    highs = np.array([float(k[2]) for k in klines], dtype=float)
    lows = np.array([float(k[3]) for k in klines], dtype=float)
    closes = np.array([float(k[4]) for k in klines], dtype=float)
    vols = np.array([float(k[5]) for k in klines], dtype=float)
    n = len(closes)
    x = np.arange(n, dtype=float)

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
        atr = np.zeros(len(c))
        atr[period] = tr[1:period + 1].mean()
        for i in range(period + 1, len(c)):
            atr[i] = (atr[i - 1] * (period - 1) + tr[i]) / period
        dxs = []
        for i in range(period, len(c)):
            atr_v = atr[i] if atr[i] > 0 else 1e-9
            di_p = 100 * (dp[i - period + 1:i + 1].mean()) / atr_v
            di_m = 100 * (dm[i - period + 1:i + 1].mean()) / atr_v
            s = di_p + di_m
            dx = 0 if s == 0 else 100 * abs(di_p - di_m) / s
            dxs.append(dx)
            out[i] = float(np.mean(dxs[-period:])) if len(dxs) >= period else dx
        return out

    ema20 = _ema(closes, 20)
    ema50 = _ema(closes, 50) if n >= 50 else _ema(closes, max(10, n // 3))
    ema100 = _ema(closes, 100) if n >= 100 else None
    bb_period = 20
    sma = np.array([closes[max(0, i - bb_period + 1):i + 1].mean() for i in range(n)])
    std = np.array([closes[max(0, i - bb_period + 1):i + 1].std() for i in range(n)])
    bb_u, bb_l = sma + 2 * std, sma - 2 * std
    rsi = _rsi_arr(closes, 14)
    adx = _adx_arr(highs, lows, closes, 14)

    # رنگ‌های حرفه‌ای
    C_UP = "#26a69a"
    C_DN = "#ef5350"
    C_EMA20 = "#42a5f5"
    C_EMA50 = "#ffa726"
    C_EMA100 = "#ab47bc"
    C_BB = "#5c6bc0"
    C_GRID = "#1e222d"
    C_TEXT = "#d1d4dc"
    C_MUTED = "#787b86"

    try:
        fig = plt.figure(figsize=(12, 9), dpi=140)
        gs = fig.add_gridspec(4, 1, height_ratios=[3.4, 0.85, 0.85, 0.85], hspace=0.06)
        ax_p = fig.add_subplot(gs[0])
        ax_v = fig.add_subplot(gs[1], sharex=ax_p)
        ax_a = fig.add_subplot(gs[2], sharex=ax_p)
        ax_r = fig.add_subplot(gs[3], sharex=ax_p)

        for ax in (ax_p, ax_v, ax_a, ax_r):
            ax.set_facecolor("#131722")
            ax.tick_params(colors=C_MUTED, labelsize=8)
            ax.grid(True, color=C_GRID, linewidth=0.7)
            for spine in ax.spines.values():
                spine.set_color("#2a2e39")

        # Bollinger fill
        ax_p.fill_between(x, bb_l, bb_u, color=C_BB, alpha=0.12, zorder=1)
        ax_p.plot(x, bb_u, color=C_BB, linewidth=0.7, alpha=0.5, linestyle="--", zorder=2)
        ax_p.plot(x, bb_l, color=C_BB, linewidth=0.7, alpha=0.5, linestyle="--", zorder=2)
        ax_p.plot(x, sma, color=C_BB, linewidth=0.9, alpha=0.7, zorder=2)

        # Candles — wick + body تمیز
        width = 0.62
        for i in range(n):
            up = closes[i] >= opens[i]
            color = C_UP if up else C_DN
            ax_p.plot([i, i], [lows[i], highs[i]], color=color, linewidth=1.0, solid_capstyle="round", zorder=3)
            body = abs(closes[i] - opens[i])
            bottom = min(opens[i], closes[i])
            if body < (highs[i] - lows[i]) * 0.002:
                body = max((highs[i] - lows[i]) * 0.015, closes[i] * 0.00008)
            ax_p.add_patch(Rectangle(
                (i - width / 2, bottom), width, body,
                facecolor=color, edgecolor=color, linewidth=0.4, zorder=4, alpha=0.95,
            ))

        ax_p.plot(x, ema20, color=C_EMA20, linewidth=1.35, label="EMA 20", zorder=5)
        ax_p.plot(x, ema50, color=C_EMA50, linewidth=1.35, label="EMA 50", zorder=5)
        if ema100 is not None:
            ax_p.plot(x, ema100, color=C_EMA100, linewidth=1.2, label="EMA 100", zorder=5)

        last = float(closes[-1])
        chg = ((closes[-1] - closes[0]) / closes[0] * 100) if closes[0] else 0
        chg_c = C_UP if chg >= 0 else C_DN
        ax_p.set_title(
            f"{pair}   •   {days}D ({interval})   •   ${last:,.2f}   ({chg:+.2f}%)",
            fontsize=13, fontweight="bold", color=C_TEXT, loc="left", pad=10,
        )
        leg = ax_p.legend(loc="upper left", fontsize=8, frameon=True, fancybox=True)
        leg.get_frame().set_facecolor("#1c2030")
        leg.get_frame().set_edgecolor("#2a2e39")
        for txt in leg.get_texts():
            txt.set_color(C_TEXT)
        ax_p.set_ylabel("Price (USDT)", fontsize=9, color=C_MUTED)
        # آخرین قیمت خط افقی
        ax_p.axhline(last, color=chg_c, linewidth=0.8, linestyle=":", alpha=0.7, zorder=2)
        ax_p.margins(x=0.01)
        plt.setp(ax_p.get_xticklabels(), visible=False)

        # Volume
        vcolors = [C_UP if closes[i] >= opens[i] else C_DN for i in range(n)]
        ax_v.bar(x, vols, color=vcolors, width=0.7, alpha=0.85, zorder=3)
        ax_v.set_ylabel("Volume", fontsize=8, color=C_MUTED)
        plt.setp(ax_v.get_xticklabels(), visible=False)
        ax_v.margins(x=0.01)

        # ADX
        ax_a.plot(x, adx, color="#b2b5be", linewidth=1.25, label="ADX(14)", zorder=3)
        ax_a.axhline(25, color="#787b86", linestyle="--", linewidth=0.8, alpha=0.8)
        ax_a.fill_between(x, adx, 25, where=(~np.isnan(adx)) & (adx >= 25), color="#26a69a", alpha=0.15)
        ax_a.set_ylabel("ADX", fontsize=8, color=C_MUTED)
        ax_a.set_ylim(0, max(60, np.nanmax(adx) * 1.15 if np.nanmax(adx) == np.nanmax(adx) else 60))
        la = ax_a.legend(loc="upper left", fontsize=7, frameon=True)
        la.get_frame().set_facecolor("#1c2030")
        la.get_frame().set_edgecolor("#2a2e39")
        for txt in la.get_texts():
            txt.set_color(C_TEXT)
        plt.setp(ax_a.get_xticklabels(), visible=False)
        ax_a.margins(x=0.01)

        # RSI
        ax_r.plot(x, rsi, color="#e0e3eb", linewidth=1.25, label="RSI(14)", zorder=3)
        ax_r.axhline(70, color=C_DN, linestyle="--", linewidth=0.8, alpha=0.7)
        ax_r.axhline(30, color=C_UP, linestyle="--", linewidth=0.8, alpha=0.7)
        ax_r.axhline(50, color="#787b86", linestyle=":", linewidth=0.6, alpha=0.5)
        ax_r.fill_between(x, 70, 100, color=C_DN, alpha=0.06)
        ax_r.fill_between(x, 0, 30, color=C_UP, alpha=0.06)
        ax_r.set_ylim(0, 100)
        ax_r.set_ylabel("RSI", fontsize=8, color=C_MUTED)
        lr = ax_r.legend(loc="upper left", fontsize=7, frameon=True)
        lr.get_frame().set_facecolor("#1c2030")
        lr.get_frame().set_edgecolor("#2a2e39")
        for txt in lr.get_texts():
            txt.set_color(C_TEXT)
        ax_r.margins(x=0.01)

        # X labels
        step = max(1, n // 7)
        ticks = list(range(0, n, step))
        if n - 1 not in ticks:
            ticks.append(n - 1)
        labels = []
        for i in ticks:
            ts = int(klines[i][0])
            if ts < 1e12:
                ts *= 1000
            dt = datetime.utcfromtimestamp(ts / 1000.0)
            labels.append(dt.strftime("%m/%d" if days > 5 else "%m/%d %H:%M"))
        ax_r.set_xticks(ticks)
        ax_r.set_xticklabels(labels, rotation=0, fontsize=8, color=C_MUTED)

        fig.subplots_adjust(left=0.07, right=0.98, top=0.93, bottom=0.06)
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=140, facecolor=fig.get_facecolor(), edgecolor="none")
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
        f"${first:,.2f} → ${last:,.2f}  {emoji} {chg:+.2f}%\n"
        f"H/L: ${float(highs.max()):,.2f} / ${float(lows.min()):,.2f}"
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


async def _fetch_fear_greed(limit: int = 7):
    """شاخص ترس و طمع — امروز + میانگین چند روز"""
    try:
        async with httpx.AsyncClient(timeout=10.0) as c:
            r = await c.get("https://api.alternative.me/fng/", params={"limit": str(limit)})
            if r.status_code == 200:
                data = (r.json() or {}).get("data") or []
                if not data:
                    return None
                today = data[0]
                vals = []
                for d in data:
                    try:
                        vals.append(int(d.get("value")))
                    except Exception:
                        pass
                out = {
                    "value": today.get("value"),
                    "value_classification": today.get("value_classification"),
                    "timestamp": today.get("timestamp"),
                    "history": data,
                    "avg_7": (sum(vals) / len(vals)) if vals else None,
                    "prev": int(data[1]["value"]) if len(data) > 1 else None,
                }
                return out
    except Exception as e:
        logger.warning(f"fear greed: {e}")
    return None


def _format_fear_greed(fg) -> list:
    """خطوط فارسی کامل برای F&G"""
    if not fg:
        return ["😨 ترس و طمع: در دسترس نیست"]
    try:
        val = int(fg.get("value") or 0)
    except Exception:
        val = 0
    cls = (fg.get("value_classification") or "").strip()
    # نقشه فارسی + ایموجی
    if val <= 24:
        fa, em = "ترس شدید", "😱"
    elif val <= 44:
        fa, em = "ترس", "😨"
    elif val <= 55:
        fa, em = "خنثی", "😐"
    elif val <= 74:
        fa, em = "طمع", "😊"
    else:
        fa, em = "طمع شدید", "🤑"
    lines = [f"😨 شاخص ترس و طمع: {val}/100 — {fa} {em}"]
    if cls:
        lines.append(f"   طبقه انگلیسی: {cls}")
    prev = fg.get("prev")
    avg7 = fg.get("avg_7")
    if prev is not None:
        delta = val - int(prev)
        arrow = "↑" if delta > 0 else ("↓" if delta < 0 else "→")
        lines.append(f"   تغییر روزانه: {arrow} {delta:+d}")
    if avg7 is not None:
        lines.append(f"   میانگین ۷روز: {avg7:.0f}")
    # تفسیر معاملاتی کوتاه
    if val <= 25:
        lines.append("   تفسیر: ترس افراطی — احتمال فرصت خرید میان‌مدت (نه سیگنال ورود فوری)")
    elif val >= 75:
        lines.append("   تفسیر: طمع افراطی — احتیاط در لانگ‌های جدید")
    return lines


async def analyze_crypto(symbol: str, ai_summary: str = "", ai_guide: str = "", timeframe: str = "4h") -> str:
    """
    خلاصه کلی دقیقاً به سبک تحلیل‌گر حرفه‌ای:
    روند، حمایت/مقاومت، سیگنال، ستاپ، R:R، ریسک، وضعیت اجرا، جمع‌بندی AI، راهنما
    """
    symbol_clean = (symbol or "").lower().strip().replace(" ", "").replace("‌", "")
    for junk in ("تحلیل", "analyze", "ارز", "کریپتو"):
        if symbol_clean.startswith(junk):
            symbol_clean = symbol_clean[len(junk):].strip()
    symbol_clean = symbol_clean.replace("usdt", "").strip() or "btc"

    coin_id = await resolve_coin_id(symbol_clean)
    _sym_map = {
        "bitcoin": "BTC", "ethereum": "ETH", "binancecoin": "BNB", "solana": "SOL",
        "ripple": "XRP", "the-open-network": "TON", "dogecoin": "DOGE", "cardano": "ADA",
        "tron": "TRX", "chainlink": "LINK", "litecoin": "LTC", "polkadot": "DOT",
        "avalanche-2": "AVAX", "shiba-inu": "SHIB", "matic-network": "MATIC",
        "near": "NEAR", "pepe": "PEPE", "sui": "SUI",
    }
    pair = symbol_clean.upper().replace("USDT", "").replace("-", "") + "USDT"
    if coin_id and coin_id in _sym_map:
        pair = _sym_map[coin_id] + "USDT"
    base = pair.replace("USDT", "")

    async def _empty():
        return {}

    # تایم‌فریم تحلیل: 1h / 4h / 1d
    tf = (timeframe or "4h").lower().strip()
    if tf in ("1h", "h", "hour", "hourly", "ساعتی"):
        tf, tf_label, klimit = "1h", "ساعتی (1H)", 168
    elif tf in ("1d", "d", "day", "daily", "روزانه"):
        tf, tf_label, klimit = "1d", "روزانه (1D)", 120
    else:
        tf, tf_label, klimit = "4h", "میان‌مدت (4H)", 180

    detail_t = _fetch_coingecko_detail(coin_id) if coin_id else _empty()
    binance_t = _fetch_binance_futures(symbol_clean)
    fg_t = _fetch_fear_greed()
    klines_t = _fetch_klines_interval(pair, tf, klimit)
    fund_t = _fetch_fundamentals(coin_id, base)

    detail, binance, fg, klines, fund = await asyncio.gather(
        detail_t, binance_t, fg_t, klines_t, fund_t
    )

    md = (detail.get("market_data") or {}) if isinstance(detail, dict) else {}
    current = md.get("current_price", {}).get("usd")
    chg_24 = md.get("price_change_percentage_24h")
    chg_7d = md.get("price_change_percentage_7d")

    if isinstance(fund, dict):
        current = current or fund.get("price")

    closes, highs, lows, vols, opens = [], [], [], [], []
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
    if len(closes) >= 30:
        ta["atr"] = _atr(highs, lows, closes, 14)
        ta["patterns"] = _detect_candle_patterns(opens, highs, lows, closes)
    support, resistance = _support_resistance(closes, highs, lows, current)

    # MTF موازی
    mtf = await _mtf_bundle(pair)
    # فیلتر ADX روزانه
    if mtf.get("force_wait"):
        ta["trend"] = "خنثی"
    # اگر تضاد شدید و تایم فعلی با روزانه مخالف
    primary_dir = (mtf.get("dirs") or {}).get(
        "1H" if tf == "1h" else ("1D" if tf == "1d" else "4H"), ""
    )
    daily_dir = (mtf.get("dirs") or {}).get("1D", "")
    if mtf.get("conflict") and primary_dir in ("صعودی", "نزولی") and daily_dir in ("صعودی", "نزولی") and primary_dir != daily_dir:
        # کاهش اطمینان
        pass

    trend = ta.get("trend", "خنثی")
    if mtf.get("force_wait"):
        trend = "خنثی"
    trend_arrow = {"صعودی": "صعودی ↗️", "نزولی": "نزولی ↘️", "خنثی": "خنثی ↔️"}.get(trend, "خنثی ↔️")
    signal, signal_emoji, setup_score, rr_quality, risk_level, exec_status = _derive_signal(
        ta, chg_24, binance or {}, current=current, support=support, resistance=resistance
    )
    # اجبار صبر اگر ADX روزانه ضعیف
    if mtf.get("force_wait"):
        signal, signal_emoji = "خنثی / احتیاط", "🟡"
        setup_score = min(setup_score, 5)
        exec_status = "صبر کنید ❌ — ADX روزانه ضعیف (بازار رنج)"
        risk_level = "متوسط 🟡"
    # امتیاز MTF این تایم
    tf_key = "1H" if tf == "1h" else ("1D" if tf == "1d" else "4H")
    if mtf.get("scores", {}).get(tf_key):
        setup_score = mtf["scores"][tf_key]

    if "لانگ" in signal:
        signal_fa = f"لانگ {signal_emoji}"
    elif "شورت" in signal:
        signal_fa = f"شورت {signal_emoji}"
    else:
        signal_fa = f"{signal} {signal_emoji}"

    def fmt_p(v):
        if v is None:
            return "—"
        try:
            v = float(v)
        except Exception:
            return "—"
        if v >= 1000:
            return f"{v:,.2f}"
        if v >= 100:
            return f"{v:,.2f}"
        if v >= 1:
            return f"{v:,.2f}"
        return f"{v:,.4f}"

    # MFI تقریبی از حجم+قیمت برای متن جمع‌بندی
    mfi_note = ""
    rsi = ta.get("rsi")
    adx = ta.get("adx")
    if rsi is not None and rsi >= 60:
        mfi_note = "مومنتوم خرید نسبتاً قوی است."
    elif rsi is not None and rsi <= 40:
        mfi_note = "مومنتوم فروش غالب است."

    if not ai_summary:
        ai_summary, ai_guide = _build_smart_summary_pair(
            pair, trend, ta, support, resistance, signal, setup_score,
            chg_24, binance or {}, current, exec_status, mfi_note
        )
    if not ai_guide:
        ai_guide = _default_guide(signal, exec_status, support, resistance, current)

    # کوتاه‌سازی معقول
    if len(ai_summary) > 320:
        ai_summary = ai_summary[:320].rsplit(" ", 1)[0] + "…"
    if len(ai_guide) > 220:
        ai_guide = ai_guide[:220].rsplit(" ", 1)[0] + "…"

    lines = [
        f"▎1. 📰 خلاصه کلی — {tf_label}",
        f"🧭 روند: {trend_arrow}",
        f"🛡 حمایت کلیدی: {fmt_p(support)}",
        f"🧱 مقاومت کلیدی: {fmt_p(resistance)}",
        f"🎯 نوع سیگنال: {signal_fa}",
        f"⭐️ امتیاز کیفیت ستاپ: {setup_score}.0",
        f"⚖️ کیفیت ریوارد (R:R وزنی): {rr_quality}",
        f"⚠️ سطح ریسک (حد ضرر): {risk_level}",
        f"🔖 وضعیت اجرا: {exec_status}",
        f"📝 جمع‌بندی: {ai_summary}",
        f"ℹ️ راهنما: {ai_guide}",
    ]

    # چندتایم‌فریم
    lines.append("")
    lines.append("▎2. ⏱ امتیاز تایم‌فریم‌ها")
    sc = mtf.get("scores") or {}
    di = mtf.get("dirs") or {}
    for k in ("1H", "4H", "1D"):
        s = sc.get(k)
        d = di.get(k, "—")
        arrow = {"صعودی": "↗️", "نزولی": "↘️", "رنج/ضعیف": "↔️"}.get(d, "·")
        lines.append(f"• {k}: {s if s is not None else '—'}/10 | {d} {arrow}")
    if mtf.get("force_wait"):
        try:
            lines.append(f"⚠️ ADX روزانه: {float(mtf.get('daily_adx') or 0):.0f} < 18 → فیلتر صبر فعال")
        except Exception:
            lines.append("⚠️ ADX روزانه ضعیف → فیلتر صبر فعال")
    if mtf.get("conflict"):
        lines.append("⚠️ تضاد تایم‌فریم‌ها — اولویت با روزانه / حجم کمتر")

    pats = list(ta.get("patterns") or [])
    pats += list((mtf.get("1d") or {}).get("patterns") or [])
    pats = list(dict.fromkeys(pats))
    if pats:
        lines.append("")
        lines.append("▎3. 🕯 الگوهای کندلی")
        for p in pats[:4]:
            lines.append(f"• {p}")

    atr_v = ta.get("atr")
    if atr_v is not None:
        lines.append(f"📐 ATR(14): {atr_v:,.4f}" if atr_v < 10 else f"📐 ATR(14): {atr_v:,.2f}")

    lines.append("")
    lines.extend(_format_fear_greed(fg))

    if current is not None:
        lines.append("")
        lines.append(f"💵 قیمت لحظه‌ای: ${fmt_p(current)}")
        bits = []
        if chg_24 is not None:
            bits.append(f"۲۴س {'🟢' if chg_24>=0 else '🔴'}{chg_24:+.1f}%")
        if chg_7d is not None:
            bits.append(f"۷ر {'🟢' if chg_7d>=0 else '🔴'}{chg_7d:+.1f}%")
        if rsi is not None:
            bits.append(f"RSI {rsi:.0f}")
        if adx is not None:
            bits.append(f"ADX {adx:.0f}")
        if binance and binance.get("funding_rate") is not None:
            bits.append(f"Fund {binance['funding_rate']:+.3f}%")
        if fg:
            bits.append(f"F&G {fg.get('value')}")
        if bits:
            lines.append(" · ".join(bits))

    lines.append("")
    lines.append("⚠️ صرفاً تحلیلی/آموزشی است؛ توصیه سرمایه‌گذاری قطعی نیست.")
    return "\n".join(lines)


def _default_guide(signal, exec_status, support, resistance, current) -> str:
    if "فرصت گذشته" in (exec_status or ""):
        return (
            "قیمت از محدودهٔ مناسبِ این ستاپ عبور کرده و دیگر ورود به آن به‌صرفه نیست. "
            "دنبالش نکن؛ منتظرِ فرصت یا تحلیلِ تازه بمان."
        )
    if "صبر" in (exec_status or "") or "خنثی" in (signal or ""):
        return "الان ورود عجله‌ای توصیه نمی‌شود. صبر کن تا قیمت به حمایت/مقاومت کلیدی برسد یا شکست معتبر بدهد."
    if "لانگ" in (signal or ""):
        return "در صورت تأیید، ورود نزدیک حمایت منطقی‌تر است؛ حد ضرر زیر حمایت و هدف نزدیک مقاومت."
    if "شورت" in (signal or ""):
        return "در صورت تأیید، ورود نزدیک مقاومت منطقی‌تر است؛ حد ضرر بالای مقاومت و هدف نزدیک حمایت."
    return "قبل از ورود، حجم و کندل تأیید را چک کن و ریسک را محدود نگه دار."


def _build_smart_summary_pair(pair, trend, ta, support, resistance, signal, score,
                              chg_24, binance, current, exec_status, mfi_note=""):
    """(جمع‌بندی، راهنما)"""
    parts = []
    if trend == "نزولی":
        parts.append("روند در تایم‌فریم اخیر نزولی است و قیمت زیر میانگین‌های مهم معامله می‌شود.")
    elif trend == "صعودی":
        parts.append("روند صعودی در تایم‌فریم اخیر تثبیت شده و قیمت بالای میانگین‌های مهم قرار دارد.")
    else:
        parts.append("بازار در وضعیت رنج/خنثی است و قدرت روند محدود به نظر می‌رسد.")

    rsi = ta.get("rsi")
    adx = ta.get("adx")
    if "لانگ" in signal and support:
        parts.append("قیمت در حال پولبک یا نزدیک شدن به حمایت‌های کلیدی است.")
    elif "شورت" in signal and resistance:
        parts.append("قیمت به مقاومت‌های کلیدی نزدیک شده یا در حال تست آن‌هاست.")

    if rsi is not None:
        if rsi >= 70:
            parts.append("RSI در ناحیه اشباع خرید است.")
        elif rsi <= 30:
            parts.append("RSI در ناحیه اشباع فروش است.")
    if adx is not None and adx >= 25:
        parts.append("ADX قدرت روند را تأیید می‌کند.")
    if mfi_note:
        parts.append(mfi_note)
    if binance and binance.get("funding_rate") is not None:
        fr = binance["funding_rate"]
        if fr > 0.05:
            parts.append("فاندینگ مثبت بالا نشان‌دهنده شلوغی لانگ‌هاست.")
        elif fr < -0.05:
            parts.append("فاندینگ منفی نشان‌دهنده فشار شورت‌هاست.")

    summary = " ".join(parts)
    guide = _default_guide(signal, exec_status, support, resistance, current)
    return summary, guide


async def _fetch_fundamentals(coin_id: str | None, base: str) -> dict:
    """داده فاندامنتال از CoinGecko + DefiLlama + Global"""
    out = {}
    headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=12.0, headers=headers) as c:
            # global dominance
            try:
                rg = await c.get("https://api.coingecko.com/api/v3/global")
                if rg.status_code == 200:
                    g = (rg.json() or {}).get("data") or {}
                    out["btc_dom"] = (g.get("market_cap_percentage") or {}).get("btc")
            except Exception:
                pass
            # DefiLlama TVL by protocol slug guess
            slug_map = {
                "BTC": None, "ETH": "ethereum", "SOL": "solana", "AVAX": "avalanche",
                "DOT": "polkadot", "ADA": "cardano", "TRX": "tron", "NEAR": "near",
                "MATIC": "polygon", "ARB": "arbitrum", "OP": "optimism", "SUI": "sui",
                "TON": "ton", "LINK": "chainlink",
            }
            slug = slug_map.get(base.upper())
            if slug:
                try:
                    rt = await c.get(f"https://api.llama.fi/tvl/{slug}")
                    if rt.status_code == 200:
                        val = rt.json()
                        if isinstance(val, (int, float)) and val > 0:
                            out["tvl"] = float(val)
                except Exception:
                    pass
            # simple price fallback if needed
            if coin_id:
                try:
                    rs = await c.get(
                        "https://api.coingecko.com/api/v3/simple/price",
                        params={
                            "ids": coin_id,
                            "vs_currencies": "usd",
                            "include_market_cap": "true",
                            "include_24hr_vol": "true",
                        },
                    )
                    if rs.status_code == 200:
                        row = (rs.json() or {}).get(coin_id) or {}
                        out["price"] = row.get("usd")
                        out["mcap"] = row.get("usd_market_cap")
                        out["vol"] = row.get("usd_24h_vol")
                except Exception:
                    pass
    except Exception as e:
        logger.warning(f"fundamentals: {e}")
    return out


def _build_smart_summary(pair, trend, ta, support, resistance, signal, score, chg_24, binance, current) -> str:
    parts = []
    if trend == "نزولی":
        parts.append("بازار زیر میانگین‌ها و با مومنتوم نزولی است.")
    elif trend == "صعودی":
        parts.append("بازار بالای میانگین‌ها و مومنتوم کوتاه‌مدت صعودی دارد.")
    else:
        parts.append("بازار رنج/خنثی است و قدرت روند محدود است.")
    rsi = ta.get("rsi")
    adx = ta.get("adx")
    if rsi is not None:
        if rsi >= 70:
            parts.append("RSI اشباع خرید؛ احتمال اصلاح.")
        elif rsi <= 30:
            parts.append("RSI اشباع فروش؛ احتمال برگشت کوتاه‌مدت.")
    if adx is not None and adx >= 25:
        parts.append("ADX روند را تأیید می‌کند.")
    elif adx is not None:
        parts.append("ADX روند ضعیف را نشان می‌دهد.")
    if "شورت" in signal:
        parts.append("استراتژی: فروش در پولبک به مقاومت.")
    elif "لانگ" in signal:
        parts.append("استراتژی: خرید روی حمایت.")
    else:
        parts.append("تا شکست واضح حمایت/مقاومت صبر بهتر است.")
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



def _atr(highs, lows, closes, period: int = 14) -> float | None:
    """Average True Range"""
    if len(closes) < period + 1:
        return None
    trs = []
    for i in range(1, len(closes)):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        trs.append(tr)
    if len(trs) < period:
        return None
    return sum(trs[-period:]) / period


def _detect_candle_patterns(opens, highs, lows, closes) -> list:
    """تشخیص ساده Engulfing و Pin Bar روی آخرین کندل‌ها"""
    patterns = []
    n = len(closes)
    if n < 3 or len(opens) < n:
        return patterns
    o, h, l, c = opens[-1], highs[-1], lows[-1], closes[-1]
    po, ph, pl, pc = opens[-2], highs[-2], lows[-2], closes[-2]
    body = abs(c - o)
    range_ = max(h - l, 1e-12)
    upper = h - max(c, o)
    lower = min(c, o) - l
    prev_body = abs(pc - po)

    # Bullish Engulfing
    if pc < po and c > o and c >= po and o <= pc and body > prev_body * 0.9:
        patterns.append("پوششی صعودی (Bullish Engulfing) 🟢")
    # Bearish Engulfing
    if pc > po and c < o and c <= po and o >= pc and body > prev_body * 0.9:
        patterns.append("پوششی نزولی (Bearish Engulfing) 🔴")

    # Pin Bar / Hammer (سایه پایین بلند)
    if lower >= body * 2 and upper <= body * 0.5 and body / range_ < 0.35:
        if c >= o:
            patterns.append("پین‌بار صعودی / چکش 🟢")
        else:
            patterns.append("پین‌بار با بدنه منفی (احتیاط) 🟡")
    # Shooting Star (سایه بالا بلند)
    if upper >= body * 2 and lower <= body * 0.5 and body / range_ < 0.35:
        if c <= o:
            patterns.append("ستاره دنباله‌دار (Shooting Star) 🔴")
        else:
            patterns.append("پین‌بار معکوس (احتیاط) 🟡")

    return patterns


def _score_timeframe(ta: dict) -> tuple:
    """امتیاز 1-10 و جهت برای یک تایم‌فریم"""
    score = 5
    trend = ta.get("trend") or "خنثی"
    rsi = ta.get("rsi")
    adx = ta.get("adx") or 0
    direction = "خنثی"

    if trend == "صعودی":
        score += 2
        direction = "صعودی"
    elif trend == "نزولی":
        score += 2
        direction = "نزولی"

    if rsi is not None:
        if direction == "صعودی" and 40 <= rsi <= 68:
            score += 1
        elif direction == "نزولی" and 32 <= rsi <= 60:
            score += 1
        elif direction == "صعودی" and rsi >= 75:
            score -= 2
        elif direction == "نزولی" and rsi <= 25:
            score -= 2

    if adx >= 25:
        score += 1
    elif adx < 18:
        score -= 2
        direction = "رنج/ضعیف"

    # الگوها
    for p in ta.get("patterns") or []:
        if "صعودی" in p or "چکش" in p:
            if direction != "نزولی":
                score += 1
        if "نزولی" in p or "دنباله‌دار" in p:
            if direction != "صعودی":
                score += 1

    score = max(1, min(10, score))
    return score, direction, adx


async def _mtf_bundle(pair: str) -> dict:
    """تحلیل موازی 1H / 4H / 1D + تضاد"""
    k1, k4, kd = await asyncio.gather(
        _fetch_klines_interval(pair, "1h", 120),
        _fetch_klines_interval(pair, "4h", 120),
        _fetch_klines_interval(pair, "1d", 120),
    )

    def pack(klines):
        opens, highs, lows, closes, vols = [], [], [], [], []
        for k in klines or []:
            try:
                opens.append(float(k[1])); highs.append(float(k[2]))
                lows.append(float(k[3])); closes.append(float(k[4]))
                vols.append(float(k[5]))
            except Exception:
                continue
        if len(closes) < 30:
            return {}, opens, highs, lows, closes
        ta = _compute_ta(closes, highs, lows, vols)
        ta["atr"] = _atr(highs, lows, closes, 14)
        ta["patterns"] = _detect_candle_patterns(opens, highs, lows, closes)
        score, direction, adx = _score_timeframe(ta)
        ta["tf_score"] = score
        ta["tf_dir"] = direction
        return ta, opens, highs, lows, closes

    t1, *_ = pack(k1)
    t4, *_ = pack(k4)
    td, o_d, h_d, l_d, c_d = pack(kd)

    dirs = {
        "1H": (t1 or {}).get("tf_dir", "—"),
        "4H": (t4 or {}).get("tf_dir", "—"),
        "1D": (td or {}).get("tf_dir", "—"),
    }
    scores = {
        "1H": (t1 or {}).get("tf_score"),
        "4H": (t4 or {}).get("tf_score"),
        "1D": (td or {}).get("tf_score"),
    }

    # تضاد
    conflict = False
    bull = sum(1 for d in dirs.values() if d == "صعودی")
    bear = sum(1 for d in dirs.values() if d == "نزولی")
    if bull >= 1 and bear >= 1:
        conflict = True

    daily_adx = (td or {}).get("adx") or 0
    force_wait = daily_adx < 18 if td else False

    return {
        "1h": t1 or {},
        "4h": t4 or {},
        "1d": td or {},
        "dirs": dirs,
        "scores": scores,
        "conflict": conflict,
        "force_wait": force_wait,
        "daily_adx": daily_adx,
        "daily_klines": (o_d, h_d, l_d, c_d),
    }


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


def _derive_signal(ta: dict, chg_24, binance: dict, current=None, support=None, resistance=None):
    """سیگنال، امتیاز، R:R، ریسک، وضعیت اجرا — با تشخیص فرصت گذشته"""
    rsi = ta.get("rsi")
    adx = ta.get("adx") or 0
    trend = ta.get("trend") or "خنثی"
    score = 5
    signal = "خنثی / احتیاط"
    signal_emoji = "🟡"

    if trend == "صعودی":
        score += 2
        signal, signal_emoji = "لانگ", "🟢"
    elif trend == "نزولی":
        score += 2
        signal, signal_emoji = "شورت", "🔴"

    if rsi is not None:
        if signal == "لانگ" and 35 <= rsi <= 65:
            score += 1
        elif signal == "شورت" and 35 <= rsi <= 65:
            score += 1
        elif signal == "لانگ" and rsi >= 72:
            score -= 2
        elif signal == "شورت" and rsi <= 28:
            score -= 2
        elif signal == "لانگ" and rsi <= 35:
            score += 1
        elif signal == "شورت" and rsi >= 65:
            score += 1

    if adx >= 25:
        score += 1
    elif adx < 18:
        score -= 1
        if signal in ("لانگ", "شورت"):
            signal, signal_emoji = "خنثی / احتیاط", "🟡"

    if chg_24 is not None:
        if signal == "لانگ" and chg_24 < -5:
            score -= 1
        if signal == "شورت" and chg_24 > 5:
            score -= 1

    fr = (binance or {}).get("funding_rate")
    if fr is not None:
        if signal == "لانگ" and fr < 0:
            score += 1
        elif signal == "شورت" and fr > 0:
            score += 1
        elif signal == "لانگ" and fr > 0.05:
            score -= 1
        elif signal == "شورت" and fr < -0.05:
            score -= 1

    score = max(1, min(10, score))

    if score >= 8:
        rr = "خوب 🟢"
        risk = "کم 🟢"
    elif score >= 6:
        rr = "متوسط 🟡"
        risk = "متوسط 🟡"
    elif score >= 4:
        rr = "متوسط 🟡"
        risk = "متوسط 🟡"
    else:
        rr = "ضعیف 🔴"
        risk = "بالا 🔴"

    exec_status = "صبر کنید ❌"
    try:
        cur = float(current) if current is not None else None
        sup = float(support) if support is not None else None
        res = float(resistance) if resistance is not None else None
    except Exception:
        cur = sup = res = None

    if signal == "لانگ" and cur is not None and sup is not None and res is not None:
        span = max(res - sup, cur * 0.001)
        pos = (cur - sup) / span
        if pos >= 0.72:
            exec_status = "فرصت گذشته — منتظرِ موقعیتِ بعدی ⛔️"
            risk = "متوسط 🟡"
        elif pos <= 0.35 and score >= 6:
            exec_status = "قابل معامله ✅"
        elif score >= 7:
            exec_status = "با احتیاط ⚠️"
        else:
            exec_status = "صبر کنید ❌"
    elif signal == "شورت" and cur is not None and sup is not None and res is not None:
        span = max(res - sup, cur * 0.001)
        near_res = abs(res - cur) / span <= 0.35
        near_sup = abs(cur - sup) / span <= 0.28
        if near_sup:
            exec_status = "فرصت گذشته — منتظرِ موقعیتِ بعدی ⛔️"
            risk = "متوسط 🟡"
        elif near_res and score >= 6:
            exec_status = "قابل معامله ✅"
        elif score >= 7:
            exec_status = "با احتیاط ⚠️"
        else:
            exec_status = "صبر کنید ❌"
    else:
        if score >= 8:
            exec_status = "قابل معامله ✅"
        elif score >= 5:
            exec_status = "با احتیاط ⚠️"
        else:
            exec_status = "صبر کنید ❌"

    return signal, signal_emoji, score, rr, risk, exec_status



async def get_crypto_analysis_short(symbol: str) -> str:
    """نسخه کوتاه‌تر برای ابزار AI"""
    return await analyze_crypto(symbol)


# ─────────────────────────────────────────────────────────────────────────────
# منوی کامل تحلیل (شبیه Algo Analyzer)
# ─────────────────────────────────────────────────────────────────────────────

def get_crypto_analysis_keyboard(symbol: str) -> "InlineKeyboardMarkup":
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    s = (symbol or "btc").lower().replace("usdt", "").strip()
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("1️⃣ خلاصه کلی", callback_data=f"cx:sum:{s}"),
                InlineKeyboardButton("2️⃣ تحلیل و نمودار روزانه", callback_data=f"cx:day:{s}"),
            ],
            [
                InlineKeyboardButton("3️⃣ تحلیل و نمودار ساعتی", callback_data=f"cx:hr:{s}"),
                InlineKeyboardButton("4️⃣ توصیه معاملاتی", callback_data=f"cx:rec:{s}"),
            ],
            [
                InlineKeyboardButton("5️⃣ رادار مشتقات", callback_data=f"cx:der:{s}"),
                InlineKeyboardButton("6️⃣ ریسک و سناریوها", callback_data=f"cx:risk:{s}"),
            ],
            [
                InlineKeyboardButton("📐 سایز پوزیشن", callback_data=f"cx:pos:{s}"),
                InlineKeyboardButton("🔔 هشدار ورود", callback_data=f"cx:al:{s}"),
            ],
            [InlineKeyboardButton("🔄 بروزرسانی تحلیل", callback_data=f"cx:ref:{s}")],
        ]
    )


def _pair_from_symbol(symbol: str) -> str:
    symbol_clean = (symbol or "btc").lower().strip().replace(" ", "").replace("‌", "")
    for junk in ("تحلیل", "analyze", "ارز", "کریپتو", "usdt"):
        symbol_clean = symbol_clean.replace(junk, "")
    symbol_clean = symbol_clean.strip() or "btc"
    _sym_map = {
        "bitcoin": "BTC", "ethereum": "ETH", "binancecoin": "BNB", "solana": "SOL",
        "ripple": "XRP", "the-open-network": "TON", "dogecoin": "DOGE", "cardano": "ADA",
        "tron": "TRX", "chainlink": "LINK", "litecoin": "LTC", "polkadot": "DOT",
        "avalanche-2": "AVAX", "shiba-inu": "SHIB", "matic-network": "MATIC",
        "near": "NEAR", "pepe": "PEPE", "sui": "SUI", "btc": "BTC", "eth": "ETH",
        "sol": "SOL", "ton": "TON", "bnb": "BNB", "xrp": "XRP", "doge": "DOGE",
    }
    base = _sym_map.get(symbol_clean, symbol_clean.upper())
    if len(base) > 10:
        base = symbol_clean.upper()[:10]
    return base + "USDT"


async def trading_recommendation(symbol: str) -> str:
    """توصیه معاملاتی + حد ضرر پویا بر اساس ATR + فیلتر MTF"""
    pair = _pair_from_symbol(symbol)
    mtf = await _mtf_bundle(pair)
    binance = await _fetch_binance_futures(symbol)
    fg = await _fetch_fear_greed(7)

    ta = mtf.get("4h") or mtf.get("1h") or {}
    klines = await _fetch_klines_interval(pair, "4h", 120)
    opens, highs, lows, closes, vols = [], [], [], [], []
    for k in klines or []:
        try:
            opens.append(float(k[1]))
            highs.append(float(k[2]))
            lows.append(float(k[3]))
            closes.append(float(k[4]))
            vols.append(float(k[5]))
        except Exception:
            continue
    if len(closes) >= 30 and not ta:
        ta = _compute_ta(closes, highs, lows, vols)
        ta["atr"] = _atr(highs, lows, closes, 14)
        ta["patterns"] = _detect_candle_patterns(opens, highs, lows, closes)

    cur = closes[-1] if closes else None
    support, resistance = _support_resistance(closes, highs, lows, cur)
    signal, sem, score, rr, risk, status = _derive_signal(
        ta, None, binance or {}, current=cur, support=support, resistance=resistance
    )

    if mtf.get("force_wait"):
        signal, sem = "خنثی / احتیاط", "🟡"
        status = "صبر کنید ❌ — ADX روزانه ضعیف"
        score = min(score, 5)

    atr = ta.get("atr") or (_atr(highs, lows, closes, 14) if len(closes) > 20 else None)
    atr_mult = 1.5
    tp2 = None
    if "لانگ" in signal and support:
        entry = support
        stop = (entry - atr_mult * atr) if atr else entry * 0.985
        tp1 = resistance or ((entry + 2 * atr_mult * atr) if atr else entry * 1.03)
        tp2 = (entry + 3 * atr_mult * atr) if atr else None
    elif "شورت" in signal and resistance:
        entry = resistance
        stop = (entry + atr_mult * atr) if atr else entry * 1.015
        tp1 = support or ((entry - 2 * atr_mult * atr) if atr else entry * 0.97)
        tp2 = (entry - 3 * atr_mult * atr) if atr else None
    else:
        entry = cur
        stop = (cur - atr_mult * atr) if (cur and atr) else (cur * 0.98 if cur else None)
        tp1 = (cur + 2 * atr_mult * atr) if (cur and atr) else (cur * 1.02 if cur else None)

    def f(v):
        if v is None:
            return "—"
        try:
            v = float(v)
        except Exception:
            return "—"
        return f"{v:,.2f}" if abs(v) >= 1 else f"{v:,.6f}"

    rr_txt = rr
    try:
        if entry and stop and tp1 and entry != stop:
            risk_d = abs(float(entry) - float(stop))
            reward = abs(float(tp1) - float(entry))
            if risk_d > 0:
                rr_txt = f"{reward / risk_d:.1f} : 1"
    except Exception:
        pass

    out = [
        f"🎯 توصیه معاملاتی — {pair}",
        "────────────────────",
        f"سیگنال: {signal} {sem}",
        f"امتیاز ستاپ: {score}/10",
        f"وضعیت: {status}",
        f"ریسک: {risk} | R:R: {rr_txt}",
        "",
        "⏱ تایم‌فریم‌ها:",
    ]
    for k in ("1H", "4H", "1D"):
        out.append(
            f"  {k}: {(mtf.get('scores') or {}).get(k, '—')}/10 | {(mtf.get('dirs') or {}).get(k, '—')}"
        )
    if mtf.get("conflict"):
        out.append("⚠️ تضاد تایم‌فریم — حجم را کم کنید")
    if mtf.get("force_wait"):
        out.append("⚠️ فیلتر ADX روزانه: صبر اولویت دارد")

    out += [
        "",
        f"📍 ورود تقریبی: {f(entry)}",
        f"🛑 حد ضرر (ATR×{atr_mult}): {f(stop)}",
        f"🎯 هدف ۱: {f(tp1)}",
    ]
    if tp2:
        out.append(f"🎯 هدف ۲: {f(tp2)}")
    if atr:
        out.append(f"📐 ATR(14): {f(atr)}")
    pats = ta.get("patterns") or []
    if pats:
        out.append("🕯 الگو: " + " | ".join(pats[:2]))
    out.append("")
    out.extend(_format_fear_greed(fg))
    out.append("")
    out.append("نکته: ورود پله‌ای؛ حد ضرر را جابه‌جا نکنید.")
    out.append("⚠️ آموزشی است؛ توصیه سرمایه‌گذاری قطعی نیست.")
    return chr(10).join(out)


async def derivatives_radar(symbol: str) -> str:
    """رادار مشتقات: Funding, OI, حجم فیوچرز"""
    pair = _pair_from_symbol(symbol)
    base = pair.replace("USDT", "")
    data = await _fetch_binance_futures(symbol)
    lines = [
        f"📡 رادار مشتقات — {pair}",
        "────────────────────",
    ]
    if not data:
        lines.append("❌ داده فیوچرز در دسترس نیست (ممکن است نماد فیوچرز نداشته باشد).")
        return "\n".join(lines)

    fr = data.get("funding_rate")
    if fr is not None:
        em = "🟢" if fr > 0 else "🔴" if fr < 0 else "⚪"
        lines.append(f"Funding Rate: {em} {fr:+.4f}%")
        if fr > 0.03:
            lines.append("  → لانگ‌ها هزینه می‌دهند؛ احتمال اصلاح/فشار فروش")
        elif fr < -0.03:
            lines.append("  → شورت‌ها هزینه می‌دهند؛ احتمال اسکوییز صعودی")
        else:
            lines.append("  → فاندینگ متعادل")
    if data.get("open_interest"):
        lines.append(f"Open Interest: {data['open_interest']:,.0f}")
    if data.get("volume_24h"):
        lines.append(f"حجم فیوچرز ۲۴س: ${data['volume_24h']:,.0f}")
    if data.get("mark_price"):
        lines.append(f"Mark Price: ${data['mark_price']:,.4f}")
    if data.get("price_change_pct") is not None:
        chg = data["price_change_pct"]
        em = "🟢" if chg >= 0 else "🔴"
        lines.append(f"تغییر فیوچرز ۲۴س: {em} {chg:+.2f}%")

    lines.append("")
    lines.append("منبع: Binance Futures (نزدیک به داده‌های مشتقه)")
    lines.append("⚠️ صرفاً اطلاعاتی است.")
    return "\n".join(lines)


async def risk_scenarios(symbol: str) -> str:
    """سناریوهای صعودی/نزولی و ریسک"""
    pair = _pair_from_symbol(symbol)
    klines = await _fetch_klines_for_ta(pair, limit=120)
    closes, highs, lows, vols = [], [], [], []
    for k in klines or []:
        try:
            highs.append(float(k[2])); lows.append(float(k[3]))
            closes.append(float(k[4])); vols.append(float(k[5]))
        except Exception:
            continue
    if len(closes) < 20:
        return f"❌ داده کافی برای سناریوی {pair} نیست."

    cur = closes[-1]
    ta = _compute_ta(closes, highs, lows, vols)
    support, resistance = _support_resistance(closes, highs, lows, cur)
    atr = 0
    if len(highs) >= 15:
        trs = []
        for i in range(1, min(15, len(closes))):
            trs.append(max(highs[-i] - lows[-i], abs(highs[-i] - closes[-i - 1]), abs(lows[-i] - closes[-i - 1])))
        atr = sum(trs) / len(trs) if trs else cur * 0.02

    bull = resistance or (cur + atr * 2)
    bear = support or (cur - atr * 2)
    invalid = (support * 0.99) if support else (cur - atr * 3)

    def f(v):
        return f"{v:,.2f}" if v >= 1 else f"{v:,.6f}"

    lines = [
        f"🎲 ریسک و سناریوها — {pair}",
        "────────────────────",
        f"قیمت فعلی: ${f(cur)}",
        f"ATR تقریبی: ${f(atr)}",
        "",
        "🟢 سناریو صعودی:",
        f"  شکست مقاومت ~{f(bull)} می‌تواند مسیر رشد را باز کند.",
        f"  هدف بعدی تقریبی: ${f(bull + atr)}",
        "",
        "🔴 سناریو نزولی:",
        f"  از دست رفتن حمایت ~{f(bear)} فشار فروش را تشدید می‌کند.",
        f"  سطح خطرناک‌تر: ${f(invalid)}",
        "",
        f"روند فعلی سیستم: {ta.get('trend', '—')}",
        f"RSI: {ta.get('rsi', 0):.1f}" if ta.get("rsi") is not None else "RSI: —",
        "",
        "مدیریت ریسک: حداکثر ۱–۲٪ سرمایه در هر معامله پیشنهاد می‌شود.",
        "⚠️ سناریوها احتمالی‌اند؛ قطعی نیستند.",
    ]
    return "\n".join(lines)


def position_size_guide(symbol: str = "") -> str:
    pair = _pair_from_symbol(symbol) if symbol else "BTCUSDT"
    return (
        f"📐 محاسبه سایز پوزیشن — {pair}\n"
        "────────────────────\n"
        "فرمت پیام بعدی:\n"
        "`سرمایه حدضرر درصد`\n\n"
        "مثال:\n"
        "• `1000 2`  → سرمایه ۱۰۰۰ دلار، حد ضرر ۲٪\n"
        "• `5000 1.5` → سرمایه ۵۰۰۰، حد ضرر ۱.۵٪\n\n"
        "فرمول:\n"
        "ریسک دلاری = سرمایه × (درصد حدضرر / ۱۰۰)\n"
        "اگر فاصله ورود تا حدضرر را هم بفرستید:\n"
        "`سرمایه حدضرر٪ فاصله٪`\n"
        "مثال: `1000 1 2`\n"
        "حجم تقریبی = ریسک / فاصله٪"
    )


def calc_position_size(text: str) -> str:
    t = (text or "").translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789"))
    nums = re.findall(r"[\d]+(?:\.\d+)?", t)
    if len(nums) < 2:
        return "❌ فرمت: `1000 2` یا `1000 1 2`"
    capital = float(nums[0])
    risk_pct = float(nums[1])
    risk_usd = capital * (risk_pct / 100.0)
    lines = [
        "📐 نتیجه سایز پوزیشن",
        "────────────────────",
        f"سرمایه: ${capital:,.2f}",
        f"ریسک: {risk_pct}%",
        f"حداکثر ضرر دلاری: **${risk_usd:,.2f}**",
    ]
    if len(nums) >= 3:
        dist = float(nums[2])
        if dist > 0:
            size = risk_usd / (dist / 100.0)
            lines.append(f"فاصله حدضرر: {dist}%")
            lines.append(f"حجم تقریبی پوزیشن: **${size:,.2f}**")
            lines.append("(فرض: حرکت خلاف جهت به اندازه فاصله٪)")
    lines.append("")
    lines.append("⚠️ این فقط محاسبه ریسک است، نه سیگنال ورود.")
    return "\n".join(lines)


async def entry_alert_text(symbol: str) -> str:
    pair = _pair_from_symbol(symbol)
    klines = await _fetch_klines_for_ta(pair, limit=80)
    closes, highs, lows = [], [], []
    for k in klines or []:
        try:
            highs.append(float(k[2])); lows.append(float(k[3])); closes.append(float(k[4]))
        except Exception:
            continue
    cur = closes[-1] if closes else None
    support, resistance = _support_resistance(closes, highs, lows, cur)
    ta = _compute_ta(closes, highs, lows, [1] * len(closes)) if len(closes) >= 30 else {}
    signal, _, _, _, _, _ = _derive_signal(ta, None, {})
    level = support if "لانگ" in signal else resistance
    if level is None:
        level = cur

    def f(v):
        if v is None:
            return "—"
        return f"{v:,.2f}" if v >= 1 else f"{v:,.6f}"

    return (
        f"🔔 هشدار نقطه ورود — {pair}\n"
        "────────────────────\n"
        f"قیمت فعلی: ${f(cur)}\n"
        f"سطح پیشنهادی ورود: **${f(level)}**\n"
        f"حمایت: ${f(support)} | مقاومت: ${f(resistance)}\n\n"
        "برای ثبت هشدار، قیمت هدف را بفرستید:\n"
        f"مثال: `{f(level)}`\n\n"
        "ربات وقتی نزدیک شد می‌تواند یادآوری ثبت کند.\n"
        "⚠️ مانیتورینگ لحظه‌ای ۲۴ساعته تضمینی نیست."
    )


async def register_price_alert(user_id: int, symbol: str, price: float) -> str:
    """ثبت یادآوری متنی برای قیمت هدف"""
    pair = _pair_from_symbol(symbol)
    try:
        from bot.database import add_reminder
        from datetime import datetime, timedelta
        import pytz
        # یادآوری ۱ ساعت بعد به‌عنوان یادآور بررسی قیمت (چون قیمت‌استریم نداریم)
        tz = pytz.timezone("Asia/Tehran")
        remind_at = (datetime.now(tz) + timedelta(hours=1)).strftime("%Y-%m-%d %H:%M")
        text = f"🔔 بررسی قیمت {pair} — هدف شما: ${price:,.4f}"
        add_reminder(user_id, text, remind_at, repeat_type="once", repeat_every=0)
        return (
            f"✅ هشدار ثبت شد\n"
            f"{pair} → هدف ${price:,.4f}\n"
            f"یادآوری بررسی حدود: {remind_at}\n"
            "می‌توانید چند هدف دیگر هم بفرستید."
        )
    except Exception as e:
        return f"⚠️ ثبت هشدار ناموفق: {e}\nهدف شما: ${price:,.4f} برای {pair}"

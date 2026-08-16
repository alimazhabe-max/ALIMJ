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

    if not coins:
        coins = await _top_from_coinlore(limit)
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
    ساخت نمودار قیمت خطی — چندمنبعی:
    CoinGecko → Binance Vision → OKX
    """
    try:
        days = max(1, min(int(days or 7), 90))
    except Exception:
        days = 7

    symbol_clean = (symbol or "").lower().strip().replace(" ", "").replace("‌", "")
    for junk in ("نمودار", "chart", "قیمت", "روز", "روزه", "price"):
        symbol_clean = symbol_clean.replace(junk, "")
    symbol_clean = symbol_clean.strip() or "btc"

    coin_id = await resolve_coin_id(symbol_clean)
    # نماد صرافی
    market_sym = (SYMBOL_TO_ID.get(symbol_clean) and symbol_clean) or symbol_clean
    # اگر resolve شد، از symbol اصلی استفاده کن
    binance_sym = symbol_clean.upper().replace("USDT", "").replace("-", "") + "USDT"
    # نگاشت چند نماد خاص
    _sym_map = {
        "bitcoin": "BTC", "ethereum": "ETH", "tether": "USDT", "binancecoin": "BNB",
        "solana": "SOL", "ripple": "XRP", "the-open-network": "TON", "dogecoin": "DOGE",
        "cardano": "ADA", "tron": "TRX", "chainlink": "LINK", "litecoin": "LTC",
        "polkadot": "DOT", "avalanche-2": "AVAX", "shiba-inu": "SHIB",
        "matic-network": "MATIC", "near": "NEAR", "pepe": "PEPE", "sui": "SUI",
    }
    if coin_id and coin_id in _sym_map:
        binance_sym = _sym_map[coin_id] + "USDT"
    elif symbol_clean in _sym_map:
        binance_sym = _sym_map[symbol_clean] + "USDT"

    headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
    prices = []  # list of [ts_ms, price]
    source = ""

    # ── 1) CoinGecko ──────────────────────────────────────────
    if coin_id and not prices:
        try:
            async with httpx.AsyncClient(timeout=15.0, headers=headers) as client:
                r = await client.get(
                    f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart",
                    params={"vs_currency": "usd", "days": str(days)},
                )
                if r.status_code == 200:
                    data = r.json() or {}
                    prices = data.get("prices") or []
                    if prices:
                        source = "CoinGecko"
                else:
                    logger.warning(f"chart CG status {r.status_code}")
        except Exception as e:
            logger.warning(f"chart CG: {e}")

    # ── 2) Binance Vision (بدون بلاک جغرافیایی) ───────────────
    if len(prices) < 2:
        try:
            if days <= 2:
                interval, limit = "15m", min(200, days * 96)
            elif days <= 7:
                interval, limit = "1h", min(200, days * 24)
            elif days <= 30:
                interval, limit = "4h", min(200, days * 6)
            else:
                interval, limit = "1d", min(200, days)
            async with httpx.AsyncClient(timeout=15.0, headers=headers) as client:
                r = await client.get(
                    "https://data-api.binance.vision/api/v3/klines",
                    params={"symbol": binance_sym, "interval": interval, "limit": int(limit)},
                )
                if r.status_code == 200:
                    klines = r.json() or []
                    if klines:
                        prices = [[int(k[0]), float(k[4])] for k in klines]
                        source = "Binance"
                else:
                    logger.warning(f"chart BN vision {binance_sym}: {r.status_code}")
        except Exception as e:
            logger.warning(f"chart BN vision: {e}")

    # ── 3) OKX fallback ───────────────────────────────────────
    if len(prices) < 2:
        try:
            okx_sym = binance_sym.replace("USDT", "-USDT")
            if days <= 2:
                bar, limit = "15m", "200"
            elif days <= 7:
                bar, limit = "1H", "168"
            elif days <= 30:
                bar, limit = "4H", "180"
            else:
                bar, limit = "1D", str(min(90, days))
            async with httpx.AsyncClient(timeout=15.0, headers=headers) as client:
                r = await client.get(
                    "https://www.okx.com/api/v5/market/candles",
                    params={"instId": okx_sym, "bar": bar, "limit": limit},
                )
                if r.status_code == 200:
                    data = r.json() or {}
                    candles = data.get("data") or []
                    if candles:
                        # OKX: newest first → reverse
                        candles = list(reversed(candles))
                        prices = [[int(c[0]), float(c[4])] for c in candles]
                        source = "OKX"
                else:
                    logger.warning(f"chart OKX {okx_sym}: {r.status_code}")
        except Exception as e:
            logger.warning(f"chart OKX: {e}")

    # ── 4) CoinGecko OHLC ساده (کمتر rate-limit حساس) ────────
    if len(prices) < 2 and coin_id:
        try:
            async with httpx.AsyncClient(timeout=15.0, headers=headers) as client:
                r = await client.get(
                    f"https://api.coingecko.com/api/v3/coins/{coin_id}/ohlc",
                    params={"vs_currency": "usd", "days": str(min(days, 30))},
                )
                if r.status_code == 200:
                    ohlc = r.json() or []
                    if ohlc:
                        prices = [[int(row[0]), float(row[4])] for row in ohlc]
                        source = "CoinGecko-OHLC"
        except Exception as e:
            logger.warning(f"chart CG ohlc: {e}")

    if not prices or len(prices) < 2:
        return None, (
            "❌ داده تاریخی برای این ارز در دسترس نیست.\n"
            f"نماد امتحان‌شده: {symbol_clean.upper()} / {binance_sym}\n"
            "مثال: btc ، eth ، sol ، ton ، pepe"
        )

    # نمونه‌برداری برای خوانایی
    step = max(1, len(prices) // 48)
    sampled = prices[::step]
    if prices[-1] not in sampled:
        sampled.append(prices[-1])

    labels = []
    values = []
    for item in sampled:
        try:
            ts, price = item[0], item[1]
            # ts ممکن است ثانیه یا میلی‌ثانیه باشد
            if ts < 1e12:
                ts = ts * 1000
            dt = datetime.utcfromtimestamp(ts / 1000.0)
            if days <= 2:
                labels.append(dt.strftime("%H:%M"))
            else:
                labels.append(dt.strftime("%m/%d"))
            values.append(float(price))
        except Exception:
            continue

    if len(values) < 2:
        return None, "❌ داده کافی برای رسم نمودار نیست."

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        plt.rcParams["axes.unicode_minus"] = False
        plt.rcParams["font.family"] = "DejaVu Sans"
    except ImportError:
        return None, "❌ matplotlib نصب نیست."

    try:
        fig, ax = plt.subplots(figsize=(9, 4.8), dpi=130)
        color = "#22c55e" if values[-1] >= values[0] else "#ef4444"
        ax.plot(range(len(values)), values, color=color, linewidth=2.0)
        ax.fill_between(range(len(values)), values, alpha=0.18, color=color)
        n_ticks = min(8, len(labels))
        tick_idx = [int(i * (len(labels) - 1) / max(1, n_ticks - 1)) for i in range(n_ticks)]
        ax.set_xticks(tick_idx)
        ax.set_xticklabels([labels[i] for i in tick_idx], rotation=25, fontsize=8)
        title_sym = symbol_clean.upper()
        ax.set_title(f"{title_sym} Price — last {days} days (USD) [{source}]", fontsize=11, fontweight="bold")
        ax.set_ylabel("USD")
        ax.grid(True, alpha=0.28, linestyle="--")
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        fig.tight_layout()

        buf = io.BytesIO()
        fig.savefig(buf, format="png", bbox_inches="tight", facecolor="white")
        plt.close(fig)
        buf.seek(0)
        png = buf.read()
    except Exception as e:
        logger.error(f"matplotlib chart error: {e}")
        try:
            plt.close("all")
        except Exception:
            pass
        return None, f"❌ خطا در رسم نمودار: {e}"

    first = values[0]
    last = values[-1]
    chg = ((last - first) / first * 100) if first else 0
    emoji = "🟢" if chg >= 0 else "🔴"
    high = max(values)
    low = min(values)
    caption = (
        f"📊 {symbol_clean.upper()} — {days} day chart\n"
        f"Source: {source}\n"
        f"Start: ${first:,.4f}\n"
        f"End: ${last:,.4f}\n"
        f"High/Low: ${high:,.4f} / ${low:,.4f}\n"
        f"Change: {emoji} {chg:+.2f}%"
    )
    return png, caption


# ─────────────────────────────────────────────────────────────────────────────
# تحلیل جامع کریپتو (چندمنبعی)
# ─────────────────────────────────────────────────────────────────────────────

async def _fetch_coingecko_detail(coin_id: str) -> dict:
    try:
        async with httpx.AsyncClient(timeout=12.0, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"}) as c:
            r = await c.get(
                f"https://api.coingecko.com/api/v3/coins/{coin_id}",
                params={
                    "localization": "false",
                    "tickers": "false",
                    "market_data": "true",
                    "community_data": "true",
                    "developer_data": "false",
                },
            )
            if r.status_code == 200:
                return r.json() or {}
    except Exception as e:
        logger.warning(f"cg detail: {e}")
    return {}


async def _fetch_binance_futures(symbol: str) -> dict:
    """داده فیوچرز بایننس (جایگزین تقریبی بخشی از Coinglass): funding + OI"""
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
                t = r3.json()
                out["volume_24h"] = float(t.get("quoteVolume") or 0)
                out["price_change_pct"] = float(t.get("priceChangePercent") or 0)
    except Exception as e:
        logger.warning(f"binance futures {sym}: {e}")
    return out


async def _fetch_fear_greed() -> Optional[dict]:
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


async def _fetch_coinpaprika_ticker(coin_id: str) -> dict:
    mapping = {
        "bitcoin": "btc-bitcoin", "ethereum": "eth-ethereum", "tether": "usdt-tether",
        "binancecoin": "bnb-binance-coin", "solana": "sol-solana", "ripple": "xrp-xrp",
        "the-open-network": "ton-toncoin", "dogecoin": "doge-dogecoin", "cardano": "ada-cardano",
        "tron": "trx-tron", "chainlink": "link-chainlink", "litecoin": "ltc-litecoin",
        "polkadot": "dot-polkadot", "avalanche-2": "avax-avalanche", "shiba-inu": "shib-shiba-inu",
        "matic-network": "matic-polygon", "near": "near-near-protocol",
    }
    pid = mapping.get(coin_id)
    if not pid:
        return {}
    try:
        async with httpx.AsyncClient(timeout=10.0) as c:
            r = await c.get(f"https://api.coinpaprika.com/v1/tickers/{pid}")
            if r.status_code == 200:
                return r.json() or {}
    except Exception as e:
        logger.warning(f"paprika ticker: {e}")
    return {}


async def analyze_crypto(symbol: str) -> str:
    """
    تحلیل جامع ارز دیجیتال از چند منبع:
    - CoinGecko, Binance Futures, CoinPaprika, Fear & Greed
    """
    symbol_clean = (symbol or "").lower().strip().replace(" ", "").replace("‌", "")
    for junk in ("تحلیل", "analyze", "ارز", "کریپتو"):
        symbol_clean = symbol_clean.replace(junk, "")
    symbol_clean = symbol_clean.strip() or "btc"

    coin_id = await resolve_coin_id(symbol_clean)
    if not coin_id:
        return "❌ ارز پیدا نشد. مثال: btc ، eth ، sol ، pepe"

    detail, binance, fg, paprika = await asyncio.gather(
        _fetch_coingecko_detail(coin_id),
        _fetch_binance_futures(symbol_clean),
        _fetch_fear_greed(),
        _fetch_coinpaprika_ticker(coin_id),
    )

    md = (detail.get("market_data") or {}) if detail else {}
    current = md.get("current_price", {}).get("usd")
    mcap = md.get("market_cap", {}).get("usd")
    vol = md.get("total_volume", {}).get("usd")
    ath = md.get("ath", {}).get("usd")
    ath_change = md.get("ath_change_percentage", {}).get("usd")
    high_24 = md.get("high_24h", {}).get("usd")
    low_24 = md.get("low_24h", {}).get("usd")
    chg_1h = md.get("price_change_percentage_1h_in_currency", {}).get("usd")
    chg_24 = md.get("price_change_percentage_24h")
    chg_7d = md.get("price_change_percentage_7d")
    chg_30d = md.get("price_change_percentage_30d")
    supply = md.get("circulating_supply")
    max_supply = md.get("max_supply")
    rank = detail.get("market_cap_rank") if detail else None
    name = detail.get("name") if detail else symbol_clean.upper()
    symbol_up = (detail.get("symbol") or symbol_clean).upper() if detail else symbol_clean.upper()

    lines = [
        f"🔍 **تحلیل جامع {name} ({symbol_up})**",
        "────────────────────────",
        "📡 منابع: CoinGecko • Binance Futures • CoinPaprika • Fear&Greed",
        "",
    ]

    if current is not None:
        lines.append(f"💵 قیمت فعلی: **${current:,.6f}**" if current < 1 else f"💵 قیمت فعلی: **${current:,.2f}**")
    if rank:
        lines.append(f"🏆 رتبه مارکت‌کپ: #{rank}")
    if mcap:
        lines.append(f"🏛 مارکت‌کپ: ${mcap:,.0f}")
    if vol:
        lines.append(f"📊 حجم ۲۴س: ${vol:,.0f}")

    lines.append("")
    lines.append("📈 **تغییرات قیمت**")
    for label, val in [("۱ ساعت", chg_1h), ("۲۴ ساعت", chg_24), ("۷ روز", chg_7d), ("۳۰ روز", chg_30d)]:
        if val is not None:
            emoji = "🟢" if val >= 0 else "🔴"
            lines.append(f"  {label}: {emoji} {val:+.2f}%")

    if high_24 is not None and low_24 is not None:
        lines.append(f"  سقف/کف ۲۴س: ${high_24:,.4f} / ${low_24:,.4f}")

    if ath is not None:
        lines.append(f"  ATH: ${ath:,.2f} ({ath_change:+.1f}% از اوج)" if ath_change is not None else f"  ATH: ${ath:,.2f}")

    if binance:
        lines.append("")
        lines.append("📉 **داده فیوچرز (Binance — نزدیک به Coinglass)**")
        if "funding_rate" in binance:
            fr = binance["funding_rate"]
            fr_emoji = "🟢" if fr > 0 else "🔴" if fr < 0 else "⚪"
            lines.append(f"  Funding Rate: {fr_emoji} {fr:.4f}%")
            if fr > 0.01:
                lines.append("    → تمایل لانگ قوی (ممکن است اصلاح کوتاه‌مدت)")
            elif fr < -0.01:
                lines.append("    → تمایل شورت قوی (ممکن است شورت‌اسکوییز)")
        if "open_interest" in binance and binance["open_interest"]:
            lines.append(f"  Open Interest: {binance['open_interest']:,.0f} قرارداد")
        if "volume_24h" in binance and binance["volume_24h"]:
            lines.append(f"  حجم فیوچرز ۲۴س: ${binance['volume_24h']:,.0f}")
        if "price_change_pct" in binance:
            lines.append(f"  تغییر فیوچرز ۲۴س: {binance['price_change_pct']:+.2f}%")

    if supply:
        lines.append("")
        lines.append("🪙 **عرضه**")
        lines.append(f"  در گردش: {supply:,.0f}")
        if max_supply:
            pct = supply / max_supply * 100
            lines.append(f"  حداکثر: {max_supply:,.0f} ({pct:.1f}% عرضه شده)")

    if fg:
        lines.append("")
        lines.append("😱 **شاخص ترس و طمع بازار**")
        val = fg.get("value")
        cls = fg.get("value_classification")
        lines.append(f"  عدد: {val} — {cls}")

    lines.append("")
    lines.append("🧠 **جمع‌بندی سریع**")
    signals = []
    if chg_24 is not None:
        if chg_24 > 5:
            signals.append("رشد قوی ۲۴ساعته")
        elif chg_24 < -5:
            signals.append("افت قابل توجه ۲۴ساعته")
    if binance.get("funding_rate") is not None:
        fr = binance["funding_rate"]
        if fr > 0.03:
            signals.append("فاندینگ خیلی مثبت (احتیاط لانگ)")
        elif fr < -0.03:
            signals.append("فاندینگ خیلی منفی (احتمال اسکوییز)")
    if fg and fg.get("value"):
        try:
            v = int(fg["value"])
            if v <= 25:
                signals.append("بازار در ترس شدید")
            elif v >= 75:
                signals.append("بازار در طمع شدید")
        except Exception:
            pass
    if not signals:
        signals.append("وضعیت نسبتاً متعادل — نیاز به بررسی بیشتر")
    for s in signals:
        lines.append(f"  • {s}")

    lines.append("")
    lines.append("⚠️ این تحلیل صرفاً اطلاعاتی است و توصیه سرمایه‌گذاری نیست.")
    lines.append("💡 برای نمودار: «نمودار btc» یا «نمودار eth 30»")

    return "\n".join(lines)


async def get_crypto_analysis_short(symbol: str) -> str:
    """نسخه کوتاه‌تر برای ابزار AI"""
    return await analyze_crypto(symbol)

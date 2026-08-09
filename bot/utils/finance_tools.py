"""
مالی و بازار — ارز، سکه، کریپتو (۵۰۰ ارز برتر)، تبدیل، سود/ضرر
CoinGecko (keyless) + TGJU
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

TGJU_SLUGS = {
    "dollar": "price_dollar_rl",
    "euro": "price_eur",
    "pound": "price_gbp",
    "dirham": "price_aed",
    "lira": "price_try",
    "gold18": "geram18",
    "coin_emami": "sekee",
    "coin_bahar": "sekeb",
    "coin_half": "nim",
    "coin_quarter": "rob",
}

# نمادهای رایج فارسی/انگلیسی → CoinGecko id
SYMBOL_TO_ID = {
    "btc": "bitcoin", "bitcoin": "bitcoin", "بیتکوین": "bitcoin", "بیت‌کوین": "bitcoin",
    "eth": "ethereum", "ethereum": "ethereum", "اتریوم": "ethereum",
    "usdt": "tether", "tether": "tether", "تتر": "tether",
    "ton": "the-open-network", "toncoin": "the-open-network", "تون": "the-open-network", "تون‌کوین": "the-open-network",
    "bnb": "binancecoin", "sol": "solana", "xrp": "ripple", "ada": "cardano",
    "doge": "dogecoin", "dot": "polkadot", "matic": "matic-network", "avax": "avalanche-2",
    "link": "chainlink", "trx": "tron", "shib": "shiba-inu", "ltc": "litecoin",
    "atom": "cosmos", "uni": "uniswap", "near": "near", "apt": "aptos",
}


def pn(n):
    return str(n).translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))


async def _tgju_price(slug: str):
    key = f"tgju_{slug}"
    now = datetime.now().timestamp()
    if key in _cache and now - _cache_t.get(key, 0) < config.CACHE_TTL:
        return _cache[key]
    try:
        url = f"https://www.tgju.org/profile/{slug}"
        async with httpx.AsyncClient(timeout=8.0, headers=HEADERS, follow_redirects=True) as c:
            r = await c.get(url)
            r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        tag = soup.find(attrs={"data-col": "info.last_trade.PDrCotVal"})
        if tag:
            text = tag.get_text(strip=True).replace(",", "")
            if text.replace(".", "").isdigit():
                val = int(float(text))
                _cache[key] = val
                _cache_t[key] = now
                return val
        nums = re.findall(r"([\d,]+)", soup.get_text())
        valid = [int(n.replace(",", "")) for n in nums if n.replace(",", "").isdigit()]
        if valid:
            val = max(valid)
            if val > 1000:
                _cache[key] = val
                _cache_t[key] = now
                return val
    except Exception as e:
        logger.error(f"tgju {slug}: {e}")
    return None


async def _get_usd_rial():
    d = await _tgju_price("price_dollar_rl")
    return d  # ریال به ازای ۱ دلار


async def _crypto_simple(ids: list[str]):
    """قیمت چند ارز از CoinGecko"""
    key = "cg_" + ",".join(sorted(ids))
    now = datetime.now().timestamp()
    if key in _cache and now - _cache_t.get(key, 0) < 60:  # ۱ دقیقه برای کریپتو
        return _cache[key]
    try:
        url = "https://api.coingecko.com/api/v3/simple/price"
        params = {"ids": ",".join(ids), "vs_currencies": "usd"}
        async with httpx.AsyncClient(timeout=10.0) as c:
            r = await c.get(url, params=params)
            r.raise_for_status()
            data = r.json()
            _cache[key] = data
            _cache_t[key] = now
            return data
    except Exception as e:
        logger.error(f"coingecko simple: {e}")
        return {}


async def get_top_crypto(limit: int = 20) -> str:
    """۲۰ ارز برتر کریپتو با قیمت دلار و تومان"""
    key = f"top_crypto_{limit}"
    now = datetime.now().timestamp()
    if key in _cache and now - _cache_t.get(key, 0) < 90:
        return _cache[key]

    try:
        url = "https://api.coingecko.com/api/v3/coins/markets"
        params = {
            "vs_currency": "usd",
            "order": "market_cap_desc",
            "per_page": limit,
            "page": 1,
            "sparkline": "false",
            "price_change_percentage": "24h",
        }
        async with httpx.AsyncClient(timeout=12.0) as c:
            r = await c.get(url, params=params)
            r.raise_for_status()
            coins = r.json()

        usd_rial = await _get_usd_rial() or 0
        lines = [f"💎 **۲۰ ارز برتر کریپتو**\n(قیمت به دلار و تومان)\n"]
        for i, coin in enumerate(coins, 1):
            name = coin.get("symbol", "").upper()
            price = coin.get("current_price") or 0
            chg = coin.get("price_change_percentage_24h") or 0
            emoji = "🟢" if chg >= 0 else "🔴"
            toman = price * (usd_rial / 10) if usd_rial else 0
            if price >= 1:
                p_str = f"${price:,.2f}"
            else:
                p_str = f"${price:.6f}"
            lines.append(
                f"{pn(i)}. **{name}** {emoji} {chg:+.1f}%\n"
                f"   {p_str}  ≈  {pn(f'{toman:,.0f}')} تومان"
            )
        result = "\n".join(lines)
        _cache[key] = result
        _cache_t[key] = now
        return result
    except Exception as e:
        logger.error(f"top crypto: {e}")
        return "❌ لیست کریپتو موقتاً در دسترس نیست. کمی بعد دوباره امتحان کنید."


async def convert_crypto(amount: float, symbol: str) -> str:
    """تبدیل مقدار ارز دیجیتال به دلار و تومان (پشتیبانی ۵۰۰+ ارز)"""
    symbol = symbol.lower().strip().replace(" ", "").replace("‌", "")
    coin_id = SYMBOL_TO_ID.get(symbol)

    if not coin_id:
        # جستجو در CoinGecko
        try:
            async with httpx.AsyncClient(timeout=8.0) as c:
                r = await c.get("https://api.coingecko.com/api/v3/search", params={"query": symbol})
                data = r.json()
                coins = data.get("coins", [])
                if coins:
                    coin_id = coins[0].get("id")
        except Exception:
            pass

    if not coin_id:
        return (
            "❌ ارز پیدا نشد.\n\n"
            "مثال‌ها:\n"
            "`20 ton` یا `1.5 btc` یا `100 usdt` یا `50 eth`\n\n"
            "بیش از ۵۰۰ ارز پشتیبانی می‌شود (نام یا نماد انگلیسی)."
        )

    prices = await _crypto_simple([coin_id])
    usd_price = prices.get(coin_id, {}).get("usd")
    if not usd_price:
        return "❌ قیمت این ارز در دسترس نیست."

    total_usd = amount * usd_price
    usd_rial = await _get_usd_rial() or 0
    total_toman = total_usd * (usd_rial / 10) if usd_rial else 0

    name = coin_id.replace("-", " ").title()
    return (
        f"💎 **تبدیل کریپتو**\n\n"
        f"مقدار: **{pn(amount)} {symbol.upper()}**\n"
        f"قیمت واحد: **${usd_price:,.6f}**\n\n"
        f"💵 معادل دلاری: **${total_usd:,.2f}**\n"
        f"🇮🇷 معادل تومانی: **{pn(f'{total_toman:,.0f}')} تومان**\n"
        f"(نرخ دلار: {pn(f'{usd_rial/10:,.0f}')} تومان)" if usd_rial else ""
    )


async def full_market_prices() -> str:
    """قیمت کامل بازار + کریپتو"""
    tasks = {k: _tgju_price(v) for k, v in TGJU_SLUGS.items()}
    crypto_ids = ["bitcoin", "ethereum", "tether", "the-open-network", "binancecoin", "solana"]
    results = await asyncio.gather(*tasks.values(), return_exceptions=True)
    keys = list(tasks.keys())
    data = {}
    for k, v in zip(keys, results):
        data[k] = v if not isinstance(v, Exception) else None

    crypto_data = await _crypto_simple(crypto_ids)

    lines = ["💰 **قیمت بازار**\n"]
    labels = {
        "dollar": "💵 دلار", "euro": "💶 یورو", "pound": "💷 پوند",
        "dirham": "🇦🇪 درهم", "lira": "🇹🇷 لیر",
        "gold18": "🥇 طلای ۱۸", "coin_emami": "🪙 سکه امامی",
        "coin_bahar": "🪙 سکه بهار", "coin_half": "🪙 نیم‌سکه",
        "coin_quarter": "🪙 ربع‌سکه",
    }
    for k, label in labels.items():
        v = data.get(k)
        if v is None:
            lines.append(f"{label}: —")
        else:
            lines.append(f"{label}: {pn(f'{v:,}')} ریال")

    lines.append("\n💎 **کریپتو (دلار):**")
    crypto_labels = {
        "bitcoin": "₿ BTC", "ethereum": "Ξ ETH", "tether": "₮ USDT",
        "the-open-network": "💎 TON", "binancecoin": "🟡 BNB", "solana": "◎ SOL",
    }
    for cid, label in crypto_labels.items():
        p = crypto_data.get(cid, {}).get("usd")
        if p:
            lines.append(f"{label}: ${p:,.2f}" if p >= 1 else f"{label}: ${p:.6f}")
        else:
            lines.append(f"{label}: —")

    return "\n".join(lines)


def rial_toman(amount: float, to_toman=True) -> str:
    if to_toman:
        return f"💵 {pn(f'{amount:,.0f}')} ریال = **{pn(f'{amount/10:,.0f}')} تومان**"
    return f"💵 {pn(f'{amount:,.0f}')} تومان = **{pn(f'{amount*10:,.0f}')} ریال**"


async def convert_currency(amount: float, from_cur: str, to_cur: str) -> str:
    from_cur, to_cur = from_cur.lower(), to_cur.lower()
    d = await _get_usd_rial()

    if from_cur in ("rial", "ریال") and to_cur in ("toman", "تومان"):
        return rial_toman(amount, True)
    if from_cur in ("toman", "تومان") and to_cur in ("rial", "ریال"):
        return rial_toman(amount, False)

    if from_cur in ("usd", "دلار") and to_cur in ("rial", "ریال") and d:
        return f"${amount:,.2f} = **{pn(f'{amount * d:,.0f}')} ریال** ({pn(f'{amount * d / 10:,.0f}')} تومان)"
    if from_cur in ("rial", "ریال") and to_cur in ("usd", "دلار") and d:
        return f"{pn(f'{amount:,.0f}')} ریال = **${amount / d:,.2f}**"
    if from_cur in ("toman", "تومان") and to_cur in ("usd", "دلار") and d:
        return f"{pn(f'{amount:,.0f}')} تومان = **${amount * 10 / d:,.2f}**"
    if from_cur in ("usd", "دلار") and to_cur in ("toman", "تومان") and d:
        return f"${amount:,.2f} = **{pn(f'{amount * d / 10:,.0f}')} تومان**"

    # کریپتو
    if from_cur in SYMBOL_TO_ID or from_cur in ("btc", "eth", "ton", "usdt"):
        return await convert_crypto(amount, from_cur)

    return (
        "❌ تبدیل پشتیبانی‌شده:\n"
        "• ریال ↔ تومان\n"
        "• دلار ↔ ریال / تومان\n"
        "• کریپتو (مثال: `20 ton` یا `1 btc`)\n\n"
        "مثال: `100 دلار تومان` یا `20 ton`"
    )


def profit_loss(buy: float, sell: float, qty: float = 1) -> str:
    diff = (sell - buy) * qty
    pct = ((sell - buy) / buy * 100) if buy else 0
    emoji = "📈" if diff >= 0 else "📉"
    return (
        f"{emoji} **محاسبه سود/ضرر**\n\n"
        f"خرید: {pn(f'{buy:,.0f}')}\n"
        f"فروش: {pn(f'{sell:,.0f}')}\n"
        f"تعداد: {pn(qty)}\n\n"
        f"{'سود' if diff >= 0 else 'ضرر'}: **{pn(f'{abs(diff):,.0f}')}**\n"
        f"درصد: **{pct:+.2f}%**"
    )


def parse_profit(text: str):
    nums = re.findall(r"[\d۰-۹٠-٩]+(?:\.\d+)?", text.translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")))
    nums = [float(n) for n in nums]
    if len(nums) >= 2:
        return nums[0], nums[1], nums[2] if len(nums) > 2 else 1.0
    return None

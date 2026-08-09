"""
مالی و بازار — ارز، سکه، کریپتو، تبدیل، سود/ضرر
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

CRYPTO_IDS = {"btc": "bitcoin", "usdt": "tether", "eth": "ethereum"}


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


async def _crypto_price(coin_id: str):
    key = f"crypto_{coin_id}"
    now = datetime.now().timestamp()
    if key in _cache and now - _cache_t.get(key, 0) < config.CACHE_TTL:
        return _cache[key]
    try:
        url = f"https://api.coingecko.com/api/v3/simple/price?ids={coin_id}&vs_currencies=usd"
        async with httpx.AsyncClient(timeout=8.0) as c:
            r = await c.get(url)
            data = r.json()
            val = data.get(coin_id, {}).get("usd")
            if val:
                _cache[key] = val
                _cache_t[key] = now
                return val
    except Exception as e:
        logger.error(f"crypto {coin_id}: {e}")
    return None


async def full_market_prices() -> str:
    tasks = {k: _tgju_price(v) for k, v in TGJU_SLUGS.items()}
    crypto_tasks = {k: _crypto_price(v) for k, v in CRYPTO_IDS.items()}
    results = await asyncio.gather(*tasks.values(), *crypto_tasks.values(), return_exceptions=True)
    keys = list(tasks.keys()) + list(crypto_tasks.keys())
    data = {}
    for k, v in zip(keys, results):
        data[k] = v if not isinstance(v, Exception) else None

    lines = ["💰 **قیمت بازار**\n"]
    labels = {
        "dollar": "💵 دلار", "euro": "💶 یورو", "pound": "💷 پوند",
        "dirham": "🇦🇪 درهم", "lira": "🇹🇷 لیر",
        "gold18": "🥇 طلای ۱۸", "coin_emami": "🪙 سکه امامی",
        "coin_bahar": "🪙 سکه بهار", "coin_half": "🪙 نیم‌سکه",
        "coin_quarter": "🪙 ربع‌سکه",
        "btc": "₿ بیت‌کوین", "usdt": "₮ تتر", "eth": "Ξ اتریوم",
    }
    for k, label in labels.items():
        v = data.get(k)
        if v is None:
            lines.append(f"{label}: —")
        elif k in CRYPTO_IDS:
            lines.append(f"{label}: ${v:,.2f}")
        else:
            lines.append(f"{label}: {pn(f'{v:,}')} ریال")
    return "\n".join(lines)


def rial_toman(amount: float, to_toman=True) -> str:
    if to_toman:
        return f"💵 {pn(f'{amount:,.0f}')} ریال = **{pn(f'{amount/10:,.0f}')} تومان**"
    return f"💵 {pn(f'{amount:,.0f}')} تومان = **{pn(f'{amount*10:,.0f}')} ریال**"


async def convert_currency(amount: float, from_cur: str, to_cur: str) -> str:
    """تبدیل ساده بر اساس نرخ دلار/کریپتو"""
    from_cur, to_cur = from_cur.lower(), to_cur.lower()
    rates = {}  # به دلار
    d = await _tgju_price("price_dollar_rl")
    if d:
        rates["irr"] = 1 / (d / 10) if d else None  # تومان per USD inverted... 
        # d is rial per USD, so 1 USD = d rial = d/10 toman
        rates["usd"] = 1.0
        rates["irr_rial"] = d
        rates["irr_toman"] = d / 10

    for cid, cname in CRYPTO_IDS.items():
        p = await _crypto_price(cname)
        if p:
            rates[cid] = p

    # ساده‌سازی: فقط موارد رایج
    if from_cur in ("rial", "ریال") and to_cur in ("toman", "تومان"):
        return rial_toman(amount, True)
    if from_cur in ("toman", "تومان") and to_cur in ("rial", "ریال"):
        return rial_toman(amount, False)

    if from_cur in ("usd", "دلار") and to_cur in ("rial", "ریال") and d:
        return f"${amount:,.2f} = **{pn(f'{amount * d:,.0f}')} ریال**"
    if from_cur in ("rial", "ریال") and to_cur in ("usd", "دلار") and d:
        return f"{pn(f'{amount:,.0f}')} ریال = **${amount / d:,.2f}**"
    if from_cur in ("btc", "بیتکوین", "بیت‌کوین") and to_cur in ("usd", "دلار"):
        p = rates.get("btc")
        if p:
            return f"{amount} BTC = **${amount * p:,.2f}**"
    if from_cur in ("usd", "دلار") and to_cur in ("btc", "بیتکوین"):
        p = rates.get("btc")
        if p:
            return f"${amount:,.2f} = **{amount / p:.8f} BTC**"

    return (
        "❌ تبدیل پشتیبانی‌شده:\n"
        "• ریال ↔ تومان\n"
        "• دلار ↔ ریال\n"
        "• BTC ↔ دلار\n\n"
        "مثال: `1000000 ریال تومان` یا `100 دلار ریال`"
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

import httpx
from bs4 import BeautifulSoup
from datetime import datetime
import re
import asyncio
from bot.logger import logger
from bot.config import config

_cache_data = {}
_cache_time = {}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

async def _get_price_from_profile(slug: str) -> int | None:
    """
    استخراج قیمت از صفحه‌ی پروفایل tgju (نسخه async)
    """
    try:
        url = f"https://www.tgju.org/profile/{slug}"
        async with httpx.AsyncClient(timeout=8.0, headers=HEADERS, follow_redirects=True) as client:
            response = await client.get(url)
            response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")

        # روش ۱: پایدارترین روش (data-col)
        price_tag = soup.find(attrs={"data-col": "info.last_trade.PDrCotVal"})
        if price_tag:
            text = price_tag.get_text(strip=True).replace(",", "")
            if text and text.replace(".", "").isdigit():
                return int(float(text))

        # روش ۲
        price_tag = soup.find("span", class_=re.compile(r"value|price"))
        if price_tag:
            text = price_tag.get_text(strip=True).replace(",", "")
            if text and text.replace(".", "").isdigit():
                return int(float(text))

        # روش ۳ (fallback)
        numbers = re.findall(r"([\d,]+)", soup.get_text())
        if numbers:
            valid_numbers = [int(n.replace(",", "")) for n in numbers if n.replace(",", "").isdigit()]
            if valid_numbers:
                max_num = max(valid_numbers)
                if max_num > 100000:
                    return max_num

        logger.warning(f"Price not found for slug: {slug}")
        return None

    except Exception as e:
        logger.error(f"Error fetching tgju price for {slug}: {e}")
        return None


async def get_dollar_price() -> int | None:
    """قیمت دلار آزاد به ریال"""
    key = "dollar"
    now = datetime.now().timestamp()

    if key in _cache_data and now - _cache_time.get(key, 0) < config.CACHE_TTL:
        return _cache_data[key]

    price = await _get_price_from_profile("price_dollar_rl")
    if price:
        _cache_data[key] = price
        _cache_time[key] = now
    return price


async def get_gold18_price() -> int | None:
    """قیمت طلای ۱۸ عیار (هر گرم) به ریال"""
    key = "gold18"
    now = datetime.now().timestamp()

    if key in _cache_data and now - _cache_time.get(key, 0) < config.CACHE_TTL:
        return _cache_data[key]

    price = await _get_price_from_profile("geram18")
    if price:
        _cache_data[key] = price
        _cache_time[key] = now
    return price


async def get_market_prices() -> dict:
    """دریافت همزمان قیمت دلار و طلا (سریع‌تر)"""
    dollar, gold = await asyncio.gather(
        get_dollar_price(),
        get_gold18_price(),
        return_exceptions=True
    )
    return {
        "dollar": dollar if not isinstance(dollar, Exception) else None,
        "gold18": gold if not isinstance(gold, Exception) else None,
    }


# توابع تومان (اختیاری - اگر جایی لازم داشتی)
async def get_dollar_price_toman() -> int | None:
    price = await get_dollar_price()
    return price // 10 if price is not None else None


async def get_gold18_price_toman() -> int | None:
    price = await get_gold18_price()
    return price // 10 if price is not None else None

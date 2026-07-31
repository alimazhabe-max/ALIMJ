import requests
from bs4 import BeautifulSoup
from datetime import datetime
from bot.logger import logger
from bot.config import config

_cache_data = {}
_cache_time = {}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

def _get_price_from_profile(slug: str) -> int | None:
    """استخراج قیمت از صفحه پروفایل tgju"""
    try:
        url = f"https://www.tgju.org/profile/{slug}"
        response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")

        # روش پایدار: پیدا کردن متن «نرخ فعلی»
        for tag in soup.find_all(["span", "div", "h3", "p"]):
            text = tag.get_text(strip=True)
            if "نرخ فعلی" in text or "نرخ فعلی:" in text:
                # عدد را از متن استخراج کن
                import re
                numbers = re.findall(r"[\d,]+", text)
                if numbers:
                    price_str = numbers[-1].replace(",", "")
                    return int(price_str)

        # روش جایگزین: data-col
        price_tag = soup.find(attrs={"data-col": "info.last_trade.PDrCotVal"})
        if price_tag:
            return int(price_tag.get_text(strip=True).replace(",", ""))

        return None
    except Exception as e:
        logger.error(f"Error fetching tgju price for {slug}: {e}")
        return None


def get_dollar_price() -> int | None:
    """قیمت دلار آزاد (ریال)"""
    key = "dollar"
    now = datetime.now().timestamp()

    if key in _cache_data and now - _cache_time.get(key, 0) < config.CACHE_TTL:
        return _cache_data[key]

    price = _get_price_from_profile("price_dollar_rl")
    if price:
        _cache_data[key] = price
        _cache_time[key] = now
    return price


def get_gold18_price() -> int | None:
    """قیمت طلای ۱۸ عیار (ریال به ازای هر گرم)"""
    key = "gold18"
    now = datetime.now().timestamp()

    if key in _cache_data and now - _cache_time.get(key, 0) < config.CACHE_TTL:
        return _cache_data[key]

    price = _get_price_from_profile("geram18")
    if price:
        _cache_data[key] = price
        _cache_time[key] = now
    return price


def get_market_prices() -> dict:
    """برگرداندن هر دو قیمت با هم"""
    return {
        "dollar": get_dollar_price(),
        "gold18": get_gold18_price(),
    }

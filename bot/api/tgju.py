import requests
from bs4 import BeautifulSoup
from datetime import datetime
import re
from bot.logger import logger
from bot.config import config

_cache_data = {}
_cache_time = {}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

def _get_price_from_profile(slug: str) -> int | None:
    """
    استخراج قیمت از صفحه‌ی پروفایل tgju
    از دو روش مختلف استفاده می‌کند تا در صورت تغییر ساختار،仍有 fallback داشته باشد.
    """
    try:
        url = f"https://www.tgju.org/profile/{slug}"
        response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")

        # روش ۱: استفاده از data-col که معمولاً پایدار است
        price_tag = soup.find(attrs={"data-col": "info.last_trade.PDrCotVal"})
        if price_tag:
            text = price_tag.get_text(strip=True).replace(",", "")
            if text and text.replace(".", "").isdigit():
                return int(float(text))  # برخی مواقع اعشار هم دارد

        # روش ۲: جستجوی span با کلاس‌های رایج (مشاهده شده در سایت)
        price_tag = soup.find("span", class_=re.compile(r"value|price"))
        if price_tag:
            text = price_tag.get_text(strip=True).replace(",", "")
            if text and text.replace(".", "").isdigit():
                return int(float(text))

        # روش ۳: جستجوی المانی که عدد بزرگ دارد (آخرین راه)
        all_text = soup.get_text()
        # الگوی عدد با کاما (مثلاً ۶۰,۰۰۰,۰۰۰)
        numbers = re.findall(r"([\d,]+)", all_text)
        if numbers:
            # معمولاً بزرگترین عدد، قیمت است (چون قیمت‌ها بزرگترین عدد در صفحه هستند)
            max_num = max(int(n.replace(",", "")) for n in numbers if n.replace(",", "").isdigit())
            if max_num > 100000:  # فرض می‌کنیم قیمت کمتر از ۱۰۰ هزار نباشد
                return max_num

        logger.warning(f"Price not found for slug: {slug}")
        return None

    except Exception as e:
        logger.error(f"Error fetching tgju price for {slug}: {e}")
        return None


def get_dollar_price() -> int | None:
    """قیمت دلار آزاد به ریال"""
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
    """قیمت طلای ۱۸ عیار (هر گرم) به ریال"""
    key = "gold18"
    now = datetime.now().timestamp()

    if key in _cache_data and now - _cache_time.get(key, 0) < config.CACHE_TTL:
        return _cache_data[key]

    price = _get_price_from_profile("geram18")
    if price:
        _cache_data[key] = price
        _cache_time[key] = now
    return price


# ========== توابع جدید برای دریافت قیمت به تومان ==========
def get_dollar_price_toman() -> int | None:
    """قیمت دلار به تومان (تقسیم بر ۱۰)"""
    price = get_dollar_price()
    if price is not None:
        return price // 10  # یا round(price/10)
    return None


def get_gold18_price_toman() -> int | None:
    """قیمت طلای ۱۸ عیار به تومان (تقسیم بر ۱۰)"""
    price = get_gold18_price()
    if price is not None:
        return price // 10
    return None


def get_market_prices() -> dict:
    """برگرداندن هر دو قیمت (به ریال)"""
    return {
        "dollar": get_dollar_price(),
        "gold18": get_gold18_price(),
    }

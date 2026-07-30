import requests
from datetime import datetime
from bot.logger import logger
from bot.config import config

_cache_data = {}
_cache_time = {}

def get_weather(city):
    """دریافت آب و هوا با کش ۵ دقیقه‌ای"""
    key = city
    now = datetime.now().timestamp()

    if key in _cache_data and now - _cache_time.get(key, 0) < config.CACHE_TTL:
        return _cache_data[key]

    try:
        url = f"https://wttr.in/{city}?format=j1"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        current = data["current_condition"][0]

        result = {
            "temp": current["temp_C"],
            "condition": current["weatherDesc"][0]["value"],
            "humidity": current["humidity"]
        }

        _cache_data[key] = result
        _cache_time[key] = now
        return result
    except Exception as e:
        logger.error(f"Error fetching weather for {city}: {e}")
        return None

"""
ابزارهای ربات برای هوش مصنوعی — با سیستم ثبت خودکار (Tool Registry).

چطور قابلیت جدید اضافه کنی تا AI خودش بفهمد؟
------------------------------------------------
در ماژول قابلیت‌ات این را صدا بزن:

    from bot.services.ai_tools import register_tool

    async def my_feature(...):
        ...

    register_tool(
        name="my_feature",
        description="توضیح واضح برای مدل که چه وقت از این ابزار استفاده کند",
        parameters={
            "type": "object",
            "properties": {
                "arg1": {"type": "string", "description": "..."},
            },
            "required": ["arg1"],
        },
        handler=my_feature,  # sync یا async هر دو OK
        keywords=[r"کلمه\s*کلیدی"],  # اختیاری برای مدل‌های بدون tool
    )

بعد از import شدن آن ماژول، ابزار در TOOL_DEFINITIONS ظاهر می‌شود.
"""
from __future__ import annotations

import inspect
import json
import re
from typing import Any, Callable, Dict, List, Optional

from bot.logger import logger

# ── Registry ────────────────────────────────────────────────────────────────

_REGISTRY: Dict[str, dict] = {}


def register_tool(
    name: str,
    description: str,
    parameters: Optional[dict] = None,
    handler: Optional[Callable] = None,
    *,
    keywords: Optional[List[str]] = None,
) -> None:
    """ثبت یک ابزار برای AI. keywords برای تزریق خودکار وقتی مدل tool ندارد."""
    if not name or not handler:
        raise ValueError("name و handler الزامی‌اند")
    _REGISTRY[name] = {
        "name": name,
        "description": description,
        "parameters": parameters or {"type": "object", "properties": {}},
        "handler": handler,
        "keywords": keywords or [],
    }
    logger.debug("AI tool registered: %s", name)


def get_tool_definitions() -> List[dict]:
    """لیست tools به فرمت OpenAI/Groq."""
    out = []
    for t in _REGISTRY.values():
        out.append(
            {
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t["description"],
                    "parameters": t["parameters"],
                },
            }
        )
    return out


def parse_tool_arguments(raw: Any) -> dict:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            return json.loads(raw) if raw.strip() else {}
        except Exception:
            return {}
    return {}


async def execute_tool(name: str, arguments: dict, *, user_id: int = 0) -> str:
    entry = _REGISTRY.get(name)
    if not entry:
        return f"ابزار ناشناخته: {name}"
    handler = entry["handler"]
    args = dict(arguments or {})
    try:
        sig = inspect.signature(handler)
        if "user_id" in sig.parameters:
            args.setdefault("user_id", user_id)
        allowed = set(sig.parameters.keys())
        args = {k: v for k, v in args.items() if k in allowed}
    except Exception:
        pass

    try:
        if inspect.iscoroutinefunction(handler):
            result = await handler(**args)
        else:
            result = handler(**args)
        return str(result)[:4500] if result is not None else "نتیجه‌ای برنگشت."
    except Exception as e:
        logger.warning("tool %s failed: %s", name, e, exc_info=True)
        return f"خطا در اجرای {name}: {e}"


async def gather_context_for_prompt(user_id: int, prompt: str) -> str:
    """برای مدل‌های بدون tool calling: با کلیدواژه، ابزار مرتبط را اجرا کن."""
    text = (prompt or "").strip()
    if not text:
        return ""

    chunks: List[str] = []
    used = set()

    for name, entry in _REGISTRY.items():
        if name in used:
            continue
        kws = entry.get("keywords") or []
        if not kws:
            continue
        for kw in kws:
            try:
                if re.search(kw, text, re.I):
                    result = await execute_tool(name, {}, user_id=user_id)
                    if result and not str(result).startswith("خطا"):
                        chunks.append(f"[{name}]\n{result}")
                        used.add(name)
                    break
            except Exception as e:
                logger.warning("gather_context %s: %s", name, e)

    if not chunks:
        return ""
    return (
        "\n\n[دادهٔ زنده از قابلیت‌های ربات — فقط از این اطلاعات برای اعداد و وضعیت واقعی استفاده کن]\n"
        + "\n---\n".join(chunks[:6])
    )



def prompt_has_keyword_tool(prompt: str) -> bool:
    """True when the prompt matches at least one registered keyword tool.

    Used by streaming/fallback providers that cannot reliably perform native
    function calling. It deliberately does not execute anything.
    """
    text = (prompt or "").strip()
    if not text:
        return False
    for entry in _REGISTRY.values():
        for kw in entry.get("keywords") or []:
            try:
                if re.search(kw, text, re.I):
                    return True
            except re.error:
                continue
    return False

def list_registered_tools() -> List[str]:
    return sorted(_REGISTRY.keys())


# ── Handlers ────────────────────────────────────────────────────────────────

async def _get_weather(city: str = "", user_id: int = 0) -> str:
    from bot.api.weather import get_weather
    from bot.database import get_user_city

    city = (city or "").strip() or (get_user_city(user_id) or "تهران")
    data = get_weather(city)
    if not data:
        return f"آب‌وهوای «{city}» پیدا نشد."
    return (
        f"آب‌وهوای {city}:\n"
        f"دما: {data.get('temp')}°C\n"
        f"وضعیت: {data.get('condition')}\n"
        f"رطوبت: {data.get('humidity')}%"
    )


async def _get_weather_forecast(city: str = "", user_id: int = 0) -> str:
    from bot.features.weather.weather_extra import weather_forecast
    from bot.database import get_user_city

    city = (city or "").strip() or (get_user_city(user_id) or "تهران")
    return await weather_forecast(city)


async def _get_air_quality(city: str = "", user_id: int = 0) -> str:
    from bot.features.weather.weather_extra import air_quality
    from bot.database import get_user_city

    city = (city or "").strip() or (get_user_city(user_id) or "تهران")
    return await air_quality(city)


async def _get_prayer_times(
    city: str = "", country: str = "Iran", user_id: int = 0
) -> str:
    from bot.api.prayer import get_prayer_times
    from bot.database import get_user_city

    city = (city or "").strip() or (get_user_city(user_id) or "قم")
    data = get_prayer_times(city, country or "Iran")
    if not data:
        return f"اوقات شرعی «{city}» پیدا نشد."
    lines = [f"اوقات شرعی {city}:"]
    for k, v in data.items():
        lines.append(f"{k}: {v}")
    return "\n".join(lines)


async def _get_market_prices() -> str:
    from bot.features.market.finance import full_market_prices

    return await full_market_prices()


async def _get_top_crypto(limit: int = 10) -> str:
    from bot.features.market.finance import get_top_crypto

    return await get_top_crypto(int(limit or 10))


async def _convert_currency(amount: float, from_cur: str, to_cur: str = "") -> str:
    from bot.features.market.finance import convert_currency

    return await convert_currency(float(amount), str(from_cur), str(to_cur or ""))


async def _convert_crypto(amount: float, symbol: str) -> str:
    from bot.features.market.finance import convert_crypto

    return await convert_crypto(float(amount), str(symbol))


def _calculator(expression: str) -> str:
    from bot.features.tools.app_tools import calculator

    return calculator(expression)


def _generate_password(length: int = 16) -> str:
    from bot.features.tools.app_tools import generate_password

    return generate_password(int(length or 16))


def _count_text(text: str) -> str:
    from bot.features.tools.app_tools import count_text

    return count_text(text)


async def _world_distance(place1: str, place2: str = "") -> str:
    from bot.features.tools.app_tools import world_distance

    return await world_distance(place1, place2 or None)


def _convert_date(date_text: str) -> str:
    from bot.features.date.date_tools import parse_any_date, convert_with_weekday

    p = parse_any_date(date_text)
    if not p:
        return "تاریخ نامعتبر. مثال: 1403/05/18 یا 2024/08/09"
    return convert_with_weekday(p[0], p[1], p[2], p[3])


def _calculate_age(birth_date: str) -> str:
    from bot.features.date.date_tools import parse_shamsi
    from bot.features.date.converters import calculate_age

    p = parse_shamsi(birth_date)
    if not p:
        return "تاریخ تولد نامعتبر. مثال: 1375/03/15"
    return calculate_age(p[0], p[1], p[2])


def _birthday_countdown(birth_date: str) -> str:
    from bot.features.date.date_tools import parse_shamsi, birthday_countdown

    p = parse_shamsi(birth_date)
    if not p:
        return "تاریخ نامعتبر. مثال: 1375/03/15"
    return birthday_countdown(p[0], p[1], p[2])


def _zodiac_animal(birth_date: str) -> str:
    from bot.features.date.date_tools import parse_shamsi, zodiac_animal

    p = parse_shamsi(birth_date)
    if not p:
        return "تاریخ نامعتبر."
    return zodiac_animal(p[0], p[1], p[2])


def _lunar_age(birth_date: str) -> str:
    from bot.features.date.date_tools import parse_shamsi, lunar_age

    p = parse_shamsi(birth_date)
    if not p:
        return "تاریخ نامعتبر."
    return lunar_age(p[0], p[1], p[2])


def _world_clock() -> str:
    from bot.features.date.date_tools import world_clock

    return world_clock()


def _month_calendar() -> str:
    from bot.features.date.date_tools import month_calendar

    return month_calendar()


def _nowruz_countdown() -> str:
    from bot.features.date.date_tools import nowruz_countdown

    return nowruz_countdown()


def _search_events(query: str) -> str:
    from bot.features.date.date_tools import search_events

    return search_events(query)


def _qibla_direction(city: str = "", user_id: int = 0) -> str:
    from bot.features.religious.qibla import qibla_direction
    from bot.database import get_user_city

    city = (city or "").strip() or (get_user_city(user_id) or "تهران")
    return qibla_direction(city)


def _daily_adhkar(user_id: int = 0) -> str:
    from bot.features.religious.adhkar import daily_adhkar

    return daily_adhkar(user_id)


async def _daily_verse_hadith(user_id: int = 0) -> str:
    from bot.features.religious.verse_hadith import daily_verse_hadith

    return await daily_verse_hadith(user_id)


def _religious_countdown() -> str:
    from bot.features.religious.events import religious_countdown

    return religious_countdown()


async def _istikhara(user_id: int = 0) -> str:
    from bot.features.religious.istikhara import istikhara

    return await istikhara(user_id)


async def _hafez_fal(user_id: int = 0) -> str:
    from bot.features.fun.fun_tools import hafez_fal

    return await hafez_fal(user_id)


async def _joke(category: str = "", user_id: int = 0) -> str:
    from bot.features.fun.fun_tools import random_joke

    return random_joke(category or None, user_id)


async def _fact_of_day() -> str:
    from bot.features.fun.fun_tools import fact_of_day

    return await fact_of_day()


async def _daily_challenge() -> str:
    from bot.features.fun.fun_tools import daily_challenge

    return await daily_challenge()


def _apply_font(text: str, style_key: str = "") -> str:
    from bot.features.fonts.converter import apply_font, apply_all_fonts, list_fonts

    if not text:
        return "متنی برای تبدیل فونت نفرستادی."
    if not style_key:
        return apply_all_fonts(text)
    try:
        return apply_font(text, style_key)
    except Exception:
        return list_fonts() + "\n\n" + apply_all_fonts(text)


def _list_fonts() -> str:
    from bot.features.fonts.converter import list_fonts

    return list_fonts()


def _get_user_city(user_id: int = 0) -> str:
    from bot.database import get_user_city

    city = get_user_city(user_id) if user_id else None
    return f"شهر ثبت‌شده کاربر: {city or 'نامشخص'}"


def _city_distance(city1: str, city2: str) -> str:
    from bot.features.weather.weather_extra import city_distance

    return city_distance(city1, city2)


def _profile_summary(user_id: int = 0) -> str:
    from bot.features.profile.profile import profile_text
    from bot.database import get_user

    row = get_user(user_id) if user_id else None
    first_name = row[1] if row else "کاربر"
    return profile_text(user_id, first_name)


# ── ثبت پیش‌فرض ─────────────────────────────────────────────────────────────


async def _tool_web_search(query: str = "") -> str:
    from bot.services.ai_extras import web_search
    return await web_search(query)


def _tool_reminder(text: str = "", remind_at: str = "", user_id: int = 0) -> str:
    from bot.database import add_reminder
    add_reminder(user_id, text, remind_at)
    return f"یادآوری ثبت شد: {text} در {remind_at}"

def _register_builtin_tools() -> None:
    if _REGISTRY:
        return

    register_tool(
        name="get_weather",
        description="آب‌وهوای فعلی یک شهر. اگر شهر نگفت از شهر کاربر استفاده کن.",
        parameters={
            "type": "object",
            "properties": {"city": {"type": "string", "description": "نام شهر"}},
        },
        handler=_get_weather,
        keywords=[r"هوا|آب\s*و\s*هوا|دما|بارون|باران|آفتابی|رطوبت"],
    )
    register_tool(
        name="get_weather_forecast",
        description="پیش‌بینی آب‌وهوای چندروزه.",
        parameters={"type": "object", "properties": {"city": {"type": "string"}}},
        handler=_get_weather_forecast,
        keywords=[r"پیش\s*بینی\s*هوا|هوای\s*فردا|هوای\s*هفته"],
    )
    register_tool(
        name="get_air_quality",
        description="کیفیت هوا (AQI).",
        parameters={"type": "object", "properties": {"city": {"type": "string"}}},
        handler=_get_air_quality,
        keywords=[r"کیفیت\s*هوا|آلودگی\s*هوا|AQI"],
    )
    register_tool(
        name="get_prayer_times",
        description="اوقات شرعی شهر.",
        parameters={
            "type": "object",
            "properties": {
                "city": {"type": "string"},
                "country": {"type": "string"},
            },
        },
        handler=_get_prayer_times,
        keywords=[r"اذان|اوقات\s*شرعی|نماز\s*(صبح|ظهر|عصر|مغرب|عشاء)"],
    )
    register_tool(
        name="get_market_prices",
        description="قیمت دلار، یورو، طلا، سکه و ارز.",
        parameters={"type": "object", "properties": {}},
        handler=_get_market_prices,
        keywords=[r"قیمت|دلار|یورو|طلا|سکه|ارز|نرخ"],
    )
    register_tool(
        name="get_top_crypto",
        description="برترین رمزارزها.",
        parameters={
            "type": "object",
            "properties": {"limit": {"type": "integer"}},
        },
        handler=_get_top_crypto,
        keywords=[r"کریپتو|بیت\s*کوین|تتر|رمزارز|crypto|bitcoin"],
    )
    register_tool(
        name="convert_currency",
        description="تبدیل ارز.",
        parameters={
            "type": "object",
            "properties": {
                "amount": {"type": "number"},
                "from_cur": {"type": "string"},
                "to_cur": {"type": "string"},
            },
            "required": ["amount", "from_cur"],
        },
        handler=_convert_currency,
    )
    register_tool(
        name="convert_crypto",
        description="تبدیل رمزارز به تومان/دلار.",
        parameters={
            "type": "object",
            "properties": {
                "amount": {"type": "number"},
                "symbol": {"type": "string"},
            },
            "required": ["amount", "symbol"],
        },
        handler=_convert_crypto,
    )
    register_tool(
        name="calculator",
        description="محاسبه ریاضی.",
        parameters={
            "type": "object",
            "properties": {"expression": {"type": "string"}},
            "required": ["expression"],
        },
        handler=_calculator,
    )
    register_tool(
        name="generate_password",
        description="ساخت رمز عبور.",
        parameters={
            "type": "object",
            "properties": {"length": {"type": "integer"}},
        },
        handler=_generate_password,
        keywords=[r"رمز\s*عبور|پسورد|password"],
    )
    register_tool(
        name="count_text",
        description="شمارش کاراکتر و کلمه.",
        parameters={
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
        handler=_count_text,
    )
    register_tool(
        name="world_distance",
        description="فاصله بین دو مکان دنیا.",
        parameters={
            "type": "object",
            "properties": {
                "place1": {"type": "string"},
                "place2": {"type": "string"},
            },
            "required": ["place1"],
        },
        handler=_world_distance,
        keywords=[r"فاصله|مسافت"],
    )
    register_tool(
        name="city_distance",
        description="فاصله دو شهر.",
        parameters={
            "type": "object",
            "properties": {
                "city1": {"type": "string"},
                "city2": {"type": "string"},
            },
            "required": ["city1", "city2"],
        },
        handler=_city_distance,
    )
    register_tool(
        name="convert_date",
        description="تبدیل تاریخ شمسی/میلادی/قمری.",
        parameters={
            "type": "object",
            "properties": {"date_text": {"type": "string"}},
            "required": ["date_text"],
        },
        handler=_convert_date,
    )
    register_tool(
        name="calculate_age",
        description="محاسبه سن از تاریخ تولد شمسی.",
        parameters={
            "type": "object",
            "properties": {"birth_date": {"type": "string"}},
            "required": ["birth_date"],
        },
        handler=_calculate_age,
        keywords=[r"سن\s*من|چند\s*سالمه|محاسبه\s*سن"],
    )
    register_tool(
        name="birthday_countdown",
        description="شمارش معکوس تولد.",
        parameters={
            "type": "object",
            "properties": {"birth_date": {"type": "string"}},
            "required": ["birth_date"],
        },
        handler=_birthday_countdown,
    )
    register_tool(
        name="zodiac_animal",
        description="حیوان سال تولد.",
        parameters={
            "type": "object",
            "properties": {"birth_date": {"type": "string"}},
            "required": ["birth_date"],
        },
        handler=_zodiac_animal,
    )
    register_tool(
        name="lunar_age",
        description="سن قمری.",
        parameters={
            "type": "object",
            "properties": {"birth_date": {"type": "string"}},
            "required": ["birth_date"],
        },
        handler=_lunar_age,
    )
    register_tool(
        name="world_clock",
        description="ساعت جهانی.",
        parameters={"type": "object", "properties": {}},
        handler=_world_clock,
        keywords=[r"ساعت\s*(الان|جهان|دنیا)|world\s*clock"],
    )
    register_tool(
        name="month_calendar",
        description="تقویم ماه جاری.",
        parameters={"type": "object", "properties": {}},
        handler=_month_calendar,
        keywords=[r"تقویم\s*ماه"],
    )
    register_tool(
        name="nowruz_countdown",
        description="شمارش معکوس نوروز.",
        parameters={"type": "object", "properties": {}},
        handler=_nowruz_countdown,
        keywords=[r"نوروز"],
    )
    register_tool(
        name="search_events",
        description="جستجوی مناسبت.",
        parameters={
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
        handler=_search_events,
        keywords=[r"مناسبت"],
    )
    register_tool(
        name="qibla_direction",
        description="جهت قبله.",
        parameters={"type": "object", "properties": {"city": {"type": "string"}}},
        handler=_qibla_direction,
        keywords=[r"قبله"],
    )
    register_tool(
        name="daily_adhkar",
        description="اذکار روزانه.",
        parameters={"type": "object", "properties": {}},
        handler=_daily_adhkar,
        keywords=[r"ذکر|اذکار"],
    )
    register_tool(
        name="daily_verse_hadith",
        description="آیه و حدیث روز.",
        parameters={"type": "object", "properties": {}},
        handler=_daily_verse_hadith,
        keywords=[r"آیه|حدیث"],
    )
    register_tool(
        name="religious_countdown",
        description="مناسبت مذهبی نزدیک.",
        parameters={"type": "object", "properties": {}},
        handler=_religious_countdown,
    )
    register_tool(
        name="istikhara",
        description="استخاره با قرآن.",
        parameters={"type": "object", "properties": {}},
        handler=_istikhara,
        keywords=[r"استخاره"],
    )
    register_tool(
        name="hafez_fal",
        description="فال حافظ.",
        parameters={"type": "object", "properties": {}},
        handler=_hafez_fal,
        keywords=[r"فال\s*حافظ|حافظ"],
    )
    register_tool(
        name="joke",
        description="جوک تصادفی.",
        parameters={
            "type": "object",
            "properties": {"category": {"type": "string"}},
        },
        handler=_joke,
        keywords=[r"جوک|جک"],
    )
    register_tool(
        name="fact_of_day",
        description="دانستنی روز.",
        parameters={"type": "object", "properties": {}},
        handler=_fact_of_day,
        keywords=[r"فکت|دانستنی"],
    )
    register_tool(
        name="daily_challenge",
        description="چالش روزانه.",
        parameters={"type": "object", "properties": {}},
        handler=_daily_challenge,
        keywords=[r"چالش"],
    )
    register_tool(
        name="apply_font",
        description="تبدیل متن به فونت‌های خاص. اگر style خالی همه را نشان بده.",
        parameters={
            "type": "object",
            "properties": {
                "text": {"type": "string"},
                "style_key": {"type": "string"},
            },
            "required": ["text"],
        },
        handler=_apply_font,
        keywords=[r"فونت"],
    )
    register_tool(
        name="list_fonts",
        description="لیست فونت‌ها.",
        parameters={"type": "object", "properties": {}},
        handler=_list_fonts,
    )
    register_tool(
        name="get_user_city",
        description="شهر ثبت‌شده کاربر.",
        parameters={"type": "object", "properties": {}},
        handler=_get_user_city,
    )
    
    register_tool(
        name="web_search",
        description="جستجو در اینترنت برای اطلاعات به‌روز.",
        parameters={
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
        handler=_tool_web_search,
        keywords=[r"جستجو\s*کن|در\s*اینترنت"],
    )
    register_tool(
        name="create_reminder",
        description="ثبت یادآوری برای کاربر. remind_at باید ISO زمان تهران باشد.",
        parameters={
            "type": "object",
            "properties": {
                "text": {"type": "string"},
                "remind_at": {"type": "string", "description": "ISO datetime"},
            },
            "required": ["text", "remind_at"],
        },
        handler=_tool_reminder,
    )
    register_tool(
        name="profile_summary",
        description="پروفایل کاربر در ربات.",
        parameters={"type": "object", "properties": {}},
        handler=_profile_summary,
        keywords=[r"پروفایل"],
    )


_register_builtin_tools()


class _ToolDefsProxy(list):
    def __iter__(self):
        return iter(get_tool_definitions())

    def __len__(self):
        return len(get_tool_definitions())

    def __getitem__(self, i):
        return get_tool_definitions()[i]


TOOL_DEFINITIONS = _ToolDefsProxy()

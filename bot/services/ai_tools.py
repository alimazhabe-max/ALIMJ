"""Built-in AI tool handlers and public tool API.

Generic registry/execution machinery lives in tool_runtime.py. This facade
re-exports the historical public functions so existing imports are stable.
"""
from __future__ import annotations
from typing import Any, List

from bot.services.tool_runtime import (
    register_tool, get_registered_tool_names, get_tool_definitions,
    _REGISTRY,
    parse_tool_arguments, execute_tool, gather_context_for_prompt,
    list_registered_tools, clear_tool_cache,
)



# ── Handlers ────────────────────────────────────────────────────────────────

async def _get_weather(city: str = "", user_id: int = 0) -> str:
    from bot.api.weather import get_weather
    from bot.database import get_user_city

    city = (city or "").strip() or (get_user_city(user_id) or "تهران")
    data = await asyncio.to_thread(get_weather, city)
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


async def _search_shopping(query: str = "", source: str = "all", max_results: int = 12, min_price: int = 0, max_price: int = 0) -> str:
    from bot.features.market.shopping import search_shopping
    return await search_shopping(
        query=query, source=source, max_results=int(max_results or 12),
        min_price=int(min_price or 0), max_price=int(max_price or 0),
    )


def _shopping_price_history(query: str = "", days: int = 30) -> str:
    from bot.features.market.shopping import shopping_price_history
    return shopping_price_history(query=query, days=int(days or 30))


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



async def _analyze_crypto(symbol: str = "") -> str:
    from bot.features.market.finance import analyze_crypto
    return await analyze_crypto(str(symbol or "btc"))


async def _crypto_chart_info(symbol: str = "", days: int = 7) -> str:
    """برای AI فقط متن توضیح می‌دهد (تصویر جدا از هندلر پیام است)"""
    from bot.features.market.finance import get_crypto_chart
    png, caption = await get_crypto_chart(str(symbol or "btc"), int(days or 7))
    if png:
        return caption + "\n\n(نمودار تصویری در بخش بازار ربات در دسترس است. بنویس: نمودار " + str(symbol) + ")"
    return caption or "داده نمودار در دسترس نیست."


async def _tool_web_search(query: str = "") -> str:
    from bot.services.ai_extras import web_search
    return await web_search(query)


def _tool_reminder(
    text: str = "",
    remind_at: str = "",
    repeat_type: str = "once",
    repeat_every: int = 0,
    user_id: int = 0,
) -> str:
    from bot.database import add_reminder
    repeat_type = repeat_type or "once"
    repeat_every = max(0, int(repeat_every or 0))
    add_reminder(
        user_id, text, remind_at,
        repeat_type=repeat_type,
        repeat_every=repeat_every,
    )
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
        name="search_shopping",
        description="جستجوی سریع خرید در فروشگاه‌ها و وب؛ برای درخواست‌های خرید مستقیم از همین ابزار استفاده می‌شود.  (ترب، دیجی‌کالا، اسنپ‌شاپ، تکنولایف، ایمالز، باسلام، مقدادآی‌تی، کالاوما، ۱۹کالا، موبایل‌آی‌آر، دیجی‌استایل، مدیسه، زنبیل، گلدیران، علی‌بابا، شیپور، دیوار، اکالا، تخفیفان) + صفحات فروش اینستاگرام + کل وب. وقتی کاربر قیمت/لینک خرید/شاپ اینستاگرام یا عکس محصول می‌خواهد از این ابزار استفاده کن. اگر مدل دقیق مشخص نیست با عبارت توصیفی جستجو کن. هرگز قیمت حدسی نگو.",
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "نام، مدل، برند یا توصیف دقیق محصول برای جستجو"},
                "source": {"type": "string", "enum": ["all", "torob", "digikala", "snappshop", "technolife", "emalls", "basalam", "momtaz", "kalaoma", "19kala", "mobile", "digistyle", "modiseh", "zanbil", "goldiran", "alibaba", "sheypoor", "divar", "okala", "takhfifan", "instagram", "general"], "description": "منبع جستجو؛ all برای همه فروشگاه‌ها + اینستا + وب"},
                "max_results": {"type": "integer", "description": "حداکثر نتایج، بین 4 تا 22"},
                "min_price": {"type": "integer", "description": "حداقل قیمت تومان؛ صفر یعنی بدون فیلتر"},
                "max_price": {"type": "integer", "description": "حداکثر قیمت تومان؛ صفر یعنی بدون فیلتر"},
            },
            "required": ["query"],
        },
        handler=_search_shopping,
        keywords=[r"خرید|قیمت.*محصول|قیمت.*کفش|قیمت.*گوشی|دیجی.?کالا|ترب|فروشگاه|لینک خرید|ارزان.?ترین|قیمت روز محصول|اینستا|شاپ اینستا|فروشگاه اینستاگرام"],
    )

    register_tool(
        name="shopping_price_history",
        description="تاریخچه قیمت مشاهده‌شده محصولات از جستجوهای قبلی ربات. اگر داده کافی وجود ندارد صریحاً اعلام کن.",
        parameters={"type":"object","properties":{"query":{"type":"string","description":"نام یا مدل محصول"},"days":{"type":"integer","description":"بازه تقریبی روز"}},"required":["query"]},
        handler=_shopping_price_history,
        keywords=[r"تاریخچه قیمت|قیمت هفته قبل|قیمت ماه قبل|روند قیمت محصول|افت قیمت محصول"],
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
        description="تبدیل رمزارز به تومان/دلار. تقریباً همه ارزها پشتیبانی می‌شود.",
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
        name="analyze_crypto",
        description="تحلیل جامع ارز دیجیتال از چند منبع (CoinGecko، Binance Futures شبیه Coinglass، Fear&Greed، CoinPaprika).",
        parameters={
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "نماد مثل btc یا eth"},
            },
            "required": ["symbol"],
        },
        handler=_analyze_crypto,
        keywords=[r"تحلیل\s*(ارز|کریپتو|رمزارز)|analyze\s*crypto|تحلیل\s*بیت\s*کوین"],
    )
    register_tool(
        name="crypto_chart_info",
        description="اطلاعات نمودار قیمت ارز دیجیتال (روزهای اخیر).",
        parameters={
            "type": "object",
            "properties": {
                "symbol": {"type": "string"},
                "days": {"type": "integer"},
            },
            "required": ["symbol"],
        },
        handler=_crypto_chart_info,
        keywords=[r"نمودار\s*(قیمت|کریپتو|ارز)|chart\s*crypto"],
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
                "repeat_type": {
                    "type": "string",
                    "enum": ["once", "daily", "weekly", "monthly", "every_minutes", "every_hours"],
                },
                "repeat_every": {"type": "integer", "minimum": 0},
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


def _run_workflow_tool(steps, user_id=0):
    # Kept as a sync-compatible wrapper; the actual engine is async.
    raise RuntimeError("workflow tool must be invoked through its async handler")


async def _run_workflow_async(steps, user_id=0):
    from bot.services.workflow_engine import run_workflow
    return await run_workflow(steps, user_id=user_id)


register_tool(
    name="run_workflow",
    description="اجرای یک برنامه چندمرحله‌ای کوتاه با ابزارهای موجود. فقط وقتی چند ابزار باید به‌ترتیب اجرا شوند استفاده کن؛ حداکثر 4 مرحله. برای ارجاع به خروجی مرحله قبل از $step1، $step2 و ... استفاده کن.",
    parameters={
        "type": "object",
        "properties": {
            "steps": {
                "type": "array",
                "maxItems": 4,
                "items": {
                    "type": "object",
                    "properties": {
                        "tool": {"type": "string"},
                        "arguments": {"type": "object"},
                    },
                    "required": ["tool"],
                },
            }
        },
        "required": ["steps"],
    },
    handler=_run_workflow_async,
)



async def _run_agent(goal: str = "", user_id: int = 0) -> str:
    from bot.services.agent_engine import run_agent
    return await run_agent(goal, user_id=user_id)


register_tool(
    name="run_agent",
    description=(
        "دستیار برنامه‌ریز محدود: برای هدف‌های چندبخشی، ابزارهای موجود را خودش انتخاب و به‌ترتیب اجرا می‌کند "
        "و حداکثر یک بار مسیر امن را ترمیم می‌کند. برای اطلاعات فعلی می‌تواند retrieval وب را فعال کند. "
        "حلقه بی‌نهایت ندارد و حداکثر 4 مرحله اجرا می‌شود."
    ),
    parameters={
        "type": "object",
        "properties": {"goal": {"type": "string", "description": "هدف کامل کاربر"}},
        "required": ["goal"],
    },
    handler=_run_agent,
    keywords=[r"خودت.*برنامه|چندمرحله|دستیار.*هوشمند|agent|برنامه.?ریزی.*هوشمند"],
)

_register_builtin_tools()


def _knowledge_search(query: str = "", limit: int = 5) -> str:
    from bot.services.knowledge_base import format_knowledge_results
    return format_knowledge_results(query, limit)


register_tool(
    name="search_knowledge_base",
    description="جستجوی هوشمند در مستندات داخلی و عمومی پروژه ربات. برای پرسش درباره قابلیت‌ها، تنظیمات و نحوه کار خود ربات استفاده کن؛ اطلاعات نامرتبط یا jokes_data.json در این شاخص وجود ندارد.",
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "عبارت جستجو"},
            "limit": {"type": "integer", "minimum": 1, "maximum": 6},
        },
        "required": ["query"],
    },
    handler=_knowledge_search,
    keywords=[r"پایگاه دانش|مستندات ربات|راهنمای ربات|تنظیمات ربات|قابلیت.*ربات|knowledge base|documentation"],
)


async def _hybrid_retrieve(query: str = "", include_web: bool = False, user_id: int = 0) -> str:
    from bot.services.retrieval import hybrid_search
    return await hybrid_search(user_id, query, include_web=bool(include_web))


register_tool(
    name="hybrid_retrieve",
    description=(
        "ترکیب حافظه مرتبط کاربر و پایگاه دانش داخلی؛ در صورت نیاز و با include_web=true "
        "از جستجوی وب هم استفاده می‌کند. برای اطلاعات فعلی/قیمت/اخبار می‌تواند وب را فعال کند. "
        "در حالت عادی درخواست شبکه‌ای انجام نمی‌دهد."
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "include_web": {"type": "boolean", "description": "آیا جستجوی وب هم انجام شود؟"},
        },
        "required": ["query"],
    },
    handler=_hybrid_retrieve,
    keywords=[r"ترکیب.*منبع|حافظه.*مستندات|منابع.*مرتبط|اطلاعات.*فعلی|hybrid retrieval|rag"],
)





class _ToolDefsProxy(list):
    def __iter__(self):
        return iter(get_tool_definitions())
    def __len__(self):
        return len(get_tool_definitions())
    def __getitem__(self, i):
        return get_tool_definitions()[i]


TOOL_DEFINITIONS = _ToolDefsProxy()

"""AI router, per-user model selection, and multi-key rotation for Rooze Ziba."""
from __future__ import annotations

import asyncio
import base64
import os
import time
from collections import defaultdict, deque
from typing import Deque, Dict, List, Optional, Tuple

import httpx

from bot.logger import logger

# ── System Prompt ───────────────────────────────────────────────────────────
SYSTEM_PROMPT = os.getenv(
    "AI_SYSTEM_PROMPT",
    "تو دستیار هوشمند ربات «روز زیبا» هستی و به قابلیت‌های واقعی همین ربات دسترسی داری. "
    "با لحنی گرم، طبیعی، محترمانه و کمی شوخ‌طبع (فقط وقتی فضا مناسب است) فارسی روان صحبت کن. "
    "اگر کاربر به زبان دیگری پیام داد، دقیقاً به همان زبان پاسخ بده. "
    "پاسخ‌هایت باید کامل، مفصل و جامع باشد. هرگز جواب را خلاصه نکن مگر اینکه کاربر صریحاً بگوید «خلاصه بگو» یا «کوتاه». "
    "وقتی کاربر درباره آب‌وهوا، اوقات شرعی، قیمت ارز/طلا/کریپتو، تبدیل تاریخ، سن، قبله، اذکار، آیه و حدیث، "
    "ساعت جهانی یا فاصله شهرها می‌پرسد، از ابزارهای ربات استفاده کن یا از «دادهٔ زنده» که در پیام آمده استفاده کن؛ "
    "هرگز عدد و قیمت ساختگی نگو. "
    "اگر داده زنده در اختیار داری، همان را مبنا قرار بده و واضح جواب بده. "
    "از حاشیه‌روی بی‌ربط پرهیز کن. هدف تو این است که کاربر حس کند دستیار ربات واقعاً به همه قابلیت‌های ربات وصل است. "
    "این ربات می‌تواند جواب را با ویس (صدا) برای کاربر بفرستد. "
    "هرگز نگو که نمی‌توانی فایل صوتی بفرستی یا کاربر را به اپ دیگر ارجاع نده. "
    "اگر کاربر فقط گفت «ویس بفرست» یا «با صدا»، یک تأیید کوتاه بده مثل «حتماً، الان با ویس می‌فرستم.» — خود سیستم ویس را می‌فرستد.",
)

MAX_INPUT = int(os.getenv("AI_MAX_INPUT", "6000"))
# سقف خروجی بالاتر تا جواب‌ها کامل و مفصل باشند
MAX_OUTPUT = int(os.getenv("AI_MAX_OUTPUT", "2800"))
HISTORY_ITEMS = max(2, int(os.getenv("AI_HISTORY_ITEMS", "8")))
# timeout کمی بالاتر چون جواب‌های کامل‌تر زمان بیشتری می‌گیرند
TIMEOUT = float(os.getenv("AI_TIMEOUT", "40"))

# مدت خاموشی کلید بعد از محدودیت روزانه (ثانیه) — پیش‌فرض ۱۲ ساعت
KEY_COOLDOWN_SEC = int(os.getenv("AI_KEY_COOLDOWN_SEC", str(12 * 3600)))
# خاموشی کوتاه برای rate-limit لحظه‌ای (ثانیه)
KEY_SHORT_COOLDOWN_SEC = int(os.getenv("AI_KEY_SHORT_COOLDOWN_SEC", "90"))

_DEFAULT_ORDER = [
    x.strip().lower()
    for x in os.getenv(
        "AI_DEFAULT_ORDER",
        # groq اول چون مدل‌های instant خیلی سریع‌اند
        "groq,gemini,cerebras,cloudflare,openrouter",
    ).split(",")
    if x.strip()
]

_HISTORY: Dict[int, Deque[Tuple[str, str]]] = defaultdict(
    lambda: deque(maxlen=HISTORY_ITEMS)
)
_LOCKS: Dict[int, asyncio.Lock] = defaultdict(asyncio.Lock)
# (provider, model) — model="*" یعنی همه مدل‌های اون ارائه‌دهنده
_USER_SELECTION: Dict[int, Tuple[str, str]] = {}
# کاربران در حال خلاصه‌سازی؛ از ساخت چند task همزمان جلوگیری می‌کند.
_SUMMARY_RUNNING: set[int] = set()

# کلاینت HTTP مشترک برای اتصال مجدد و سرعت بیشتر
_HTTP: Optional[httpx.AsyncClient] = None


def _get_http() -> httpx.AsyncClient:
    global _HTTP
    if _HTTP is None or _HTTP.is_closed:
        _HTTP = httpx.AsyncClient(
            timeout=httpx.Timeout(TIMEOUT, connect=5.0),
            limits=httpx.Limits(max_keepalive_connections=20, max_connections=40),
            http2=False,
        )
    return _HTTP

async def close_http() -> None:
    """بستن کلاینت HTTP در shutdown ربات."""
    global _HTTP
    if _HTTP is not None and not _HTTP.is_closed:
        await _HTTP.aclose()
    _HTTP = None

# ── Key Pool: چند کلید + چرخش وقتی یکی تمام شد ─────────────────────────────
# key_id -> cooldown_until (unix timestamp)
_KEY_COOLDOWN: Dict[str, float] = {}
# provider -> index of last used key (round-robin)
_KEY_RR: Dict[str, int] = defaultdict(int)


def _split_keys(*env_names: str) -> List[str]:
    """از یک یا چند env، کلیدها را با کاما جدا می‌کند."""
    keys: List[str] = []
    seen = set()
    for name in env_names:
        raw = os.getenv(name, "") or ""
        for part in raw.replace(";", ",").split(","):
            k = part.strip()
            if k and k not in seen:
                seen.add(k)
                keys.append(k)
    return keys


def _provider_keys(provider: str) -> List[str]:
    if provider == "gemini":
        return _split_keys("GEMINI_API_KEY", "GEMINI_API_KEYS")
    if provider == "groq":
        return _split_keys("GROQ_API_KEY", "GROQ_API_KEYS")
    if provider == "cerebras":
        return _split_keys("CEREBRAS_API_KEY", "CEREBRAS_API_KEYS")
    if provider == "openrouter":
        return _split_keys("OPENROUTER_API_KEY", "OPENROUTER_API_KEYS")
    if provider == "cloudflare":
        # برای کلودفلر توکن‌ها؛ اکانت معمولاً یکی است
        return _split_keys("CLOUDFLARE_AUTH_TOKEN", "CLOUDFLARE_AUTH_TOKENS")
    return []


def _key_id(provider: str, key: str) -> str:
    # فقط چند کاراکتر آخر برای لاگ امن
    tail = key[-6:] if len(key) >= 6 else key
    return f"{provider}:{tail}"


def _is_key_available(kid: str) -> bool:
    until = _KEY_COOLDOWN.get(kid, 0)
    if until <= time.time():
        _KEY_COOLDOWN.pop(kid, None)
        return True
    return False


def _mark_key_cooldown(provider: str, key: str, *, daily: bool = True) -> None:
    kid = _key_id(provider, key)
    sec = KEY_COOLDOWN_SEC if daily else KEY_SHORT_COOLDOWN_SEC
    _KEY_COOLDOWN[kid] = time.time() + sec
    logger.warning(
        "AI key cooldown: %s for %ss (daily=%s)", kid, sec, daily
    )


def _is_quota_error(status: int, data) -> bool:
    """تشخیص محدودیت روزانه / سهمیه / rate limit."""
    if status in (429, 403):
        return True
    text = str(data).lower()
    markers = (
        "quota",
        "rate limit",
        "rate_limit",
        "resource exhausted",
        "resource_exhausted",
        "too many requests",
        "exceeded",
        "limit exceeded",
        "daily limit",
        "usage limit",
        "insufficient_quota",
        "tokens per day",
        "tpm",
        "rpm",
    )
    return any(m in text for m in markers)


def _next_keys(provider: str) -> List[str]:
    """
    لیست کلیدهای قابل استفاده به ترتیب round-robin.
    کلیدهای در حال cooldown آخر می‌آیند (اگر همه تمام باشند باز هم امتحان می‌شوند).
    """
    keys = _provider_keys(provider)
    if not keys:
        return []
    n = len(keys)
    start = _KEY_RR[provider] % n
    ordered = keys[start:] + keys[:start]
    available = [k for k in ordered if _is_key_available(_key_id(provider, k))]
    cooled = [k for k in ordered if not _is_key_available(_key_id(provider, k))]
    return available + cooled


def _advance_rr(provider: str) -> None:
    keys = _provider_keys(provider)
    if keys:
        _KEY_RR[provider] = (_KEY_RR[provider] + 1) % len(keys)


# ── User selection ──────────────────────────────────────────────────────────

def clear_history(user_id: int, *, clear_long_term: bool = False) -> None:
    _HISTORY.pop(user_id, None)
    try:
        from bot.database import clear_ai_history_summary, delete_ai_memory
        clear_ai_history_summary(user_id)
        if clear_long_term:
            delete_ai_memory(user_id)
    except Exception:
        pass


def get_selected_model(user_id: int) -> Tuple[str, str] | None:
    if user_id in _USER_SELECTION:
        return _USER_SELECTION[user_id]
    try:
        from bot.database import get_ai_preference
        pref = get_ai_preference(user_id)
        if pref:
            _USER_SELECTION[user_id] = pref
            return pref
    except Exception as e:
        logger.warning("get_ai_preference failed: %s", e)
    return None


def set_selected_model(user_id: int, provider: str, model: str) -> None:
    _USER_SELECTION[user_id] = (provider, model)
    try:
        from bot.database import set_ai_preference
        set_ai_preference(user_id, provider, model)
    except Exception as e:
        logger.warning("set_ai_preference failed: %s", e)


def clear_selected_model(user_id: int) -> None:
    _USER_SELECTION.pop(user_id, None)
    try:
        from bot.database import clear_ai_preference
        clear_ai_preference(user_id)
    except Exception as e:
        logger.warning("clear_ai_preference failed: %s", e)


def _env_models(env_name: str, default: List[str]) -> List[str]:
    raw = os.getenv(env_name, "")
    values = [x.strip() for x in raw.split(",") if x.strip()]
    return values or default


def available_model_options() -> List[Tuple[str, str, str]]:
    """همه مدل‌ها به ترتیب ارائه‌دهنده و سرعت (سریع‌ترین اول)."""
    raw: Dict[str, List[Tuple[str, str, str]]] = {}

    if _provider_keys("gemini"):
        items = []
        # مدل‌های پایدار جدید؛ Lite برای سرعت، 3.6 برای کیفیت
        for model in _env_models(
            "GEMINI_MODELS",
            ["gemini-3.6-flash", "gemini-3.5-flash-lite", "gemini-3.1-flash-lite"],
        ):
            label = "Gemini • " + model.replace("gemini-", "Gemini ")
            items.append(("gemini", label, model))
        raw["gemini"] = items

    if _provider_keys("groq"):
        items = []
        # instant اول = خیلی سریع
        for model in _env_models(
            "GROQ_MODELS",
            [
                "llama-3.1-8b-instant",
                "openai/gpt-oss-20b",
                "llama-3.3-70b-versatile",
                "openai/gpt-oss-120b",
            ],
        ):
            items.append(("groq", "Groq • " + model, model))
        raw["groq"] = items

    if _provider_keys("cerebras"):
        items = []
        for model in _env_models(
            "CEREBRAS_MODELS",
            [os.getenv("CEREBRAS_MODEL", "gpt-oss-120b")],
        ):
            items.append(("cerebras", "Cerebras • " + model, model))
        raw["cerebras"] = items

    if os.getenv("CLOUDFLARE_ACCOUNT_ID") and _provider_keys("cloudflare"):
        items = []
        for model in _env_models(
            "CLOUDFLARE_MODELS",
            [os.getenv("CLOUDFLARE_MODEL", "@cf/meta/llama-3.2-3b-instruct")],
        ):
            items.append(("cloudflare", "Cloudflare • " + model, model))
        raw["cloudflare"] = items

    if _provider_keys("openrouter"):
        items = []
        for model in _env_models(
            "OPENROUTER_MODELS",
            [os.getenv("OPENROUTER_MODEL", "openrouter/free")],
        ):
            items.append(("openrouter", "OpenRouter • " + model, model))
        raw["openrouter"] = items

    ordered: List[Tuple[str, str, str]] = []
    seen = set()
    for p in _DEFAULT_ORDER:
        if p in raw and p not in seen:
            ordered.extend(raw[p])
            seen.add(p)
    for p, items in raw.items():
        if p not in seen:
            ordered.extend(items)
    return ordered


_PROVIDER_PRETTY = {
    "gemini": "Gemini",
    "groq": "Groq",
    "cerebras": "Cerebras",
    "cloudflare": "Cloudflare",
    "openrouter": "OpenRouter",
}


def available_providers() -> List[Tuple[str, str]]:
    """
    لیست ارائه‌دهنده‌های فعال برای دکمهٔ انتخاب.
    هر آیتم: (provider_id, label)
    با انتخاب یک ارائه‌دهنده، همه مدل‌هایش به‌صورت خودکار امتحان می‌شوند.
    """
    options = available_model_options()
    by_provider: Dict[str, int] = {}
    for provider, _label, _model in options:
        by_provider[provider] = by_provider.get(provider, 0) + 1

    result: List[Tuple[str, str]] = []
    seen = set()
    for p in _DEFAULT_ORDER:
        if p in by_provider and p not in seen:
            pretty = _PROVIDER_PRETTY.get(p, p)
            n = by_provider[p]
            keys = len(_provider_keys(p))
            suffix = f" ({n} مدل)" if n > 1 else ""
            if keys > 1:
                suffix += f" ×{keys} کلید"
            result.append((p, f"{pretty}{suffix}"))
            seen.add(p)
    for p, n in by_provider.items():
        if p not in seen:
            pretty = _PROVIDER_PRETTY.get(p, p)
            suffix = f" ({n} مدل)" if n > 1 else ""
            result.append((p, f"{pretty}{suffix}"))
    return result


def models_for_provider(provider: str) -> List[str]:
    """مدل‌های یک ارائه‌دهنده به ترتیب سرعت (اول = سریع‌تر)."""
    return [m for p, _l, m in available_model_options() if p == provider]


def enabled_providers() -> List[str]:
    return [label for _p, label in available_providers()]


def default_model_info() -> str:
    providers = available_providers()
    if not providers:
        return "هیچ"
    return providers[0][1]


def set_selected_provider(user_id: int, provider: str) -> None:
    """انتخاب ارائه‌دهنده — همه مدل‌هایش شامل می‌شوند (model='*')."""
    set_selected_model(user_id, provider, "*")


def key_pool_status() -> str:
    """برای ادمین: وضعیت کلیدها."""
    lines = []
    for provider in ("gemini", "groq", "cerebras", "openrouter", "cloudflare"):
        keys = _provider_keys(provider)
        if not keys:
            continue
        avail = sum(1 for k in keys if _is_key_available(_key_id(provider, k)))
        lines.append(f"{provider}: {avail}/{len(keys)} فعال")
    return "\n".join(lines) if lines else "هیچ کلیدی تنظیم نشده"


def _memory_block(user_id: int) -> str:
    """بلوک حافظه بلندمدت + خلاصه تاریخچه برای تزریق به سیستم."""
    parts = []
    try:
        from bot.database import get_ai_memory, get_ai_history_summary
        mem = get_ai_memory(user_id, limit=30)
        if mem:
            lines = [f"- {k}: {v}" for k, v in mem]
            parts.append("حافظه بلندمدت درباره این کاربر:\n" + "\n".join(lines))
        summary = get_ai_history_summary(user_id)
        if summary:
            parts.append("خلاصه گفتگوهای قبلی:\n" + summary)
    except Exception as e:
        logger.warning("memory_block: %s", e)
    return "\n\n".join(parts)


def _extract_and_store_memory(user_id: int, prompt: str) -> None:
    """اگر کاربر گفت چیزی را به خاطر بسپار، ذخیره کن."""
    import re
    t = (prompt or "").strip()
    m = re.search(
        r"(?:یادت\s*باشه|به\s*خاطر\s*بسپار|یادت\s*باشه\s*که|من\s*(?:اسمم|نامم)\s*)[:：]?\s*(.+)$",
        t,
        re.I | re.S,
    )
    if not m:
        m2 = re.search(r"اسمم\s+([^\n.،,]{2,40})", t)
        if m2:
            try:
                from bot.database import set_ai_memory
                set_ai_memory(user_id, "name", m2.group(1).strip())
            except Exception:
                pass
        return
    fact = m.group(1).strip()[:500]
    if not fact:
        return
    key = "note"
    if re.search(r"اسم|نام", t):
        key = "name"
    elif re.search(r"شهر|زندگی", t):
        key = "city"
    elif re.search(r"علاقه|دوست\s*دارم", t):
        key = "interest"
    try:
        from bot.database import set_ai_memory
        set_ai_memory(user_id, key, fact)
    except Exception as e:
        logger.warning("store memory: %s", e)


async def _maybe_summarize_history(user_id: int) -> None:
    """وقتی تاریخچه پر شد، یک‌بار خلاصه می‌سازد و بخش قدیمی را سبک می‌کند."""
    history = _HISTORY[user_id]
    if len(history) < HISTORY_ITEMS or user_id in _SUMMARY_RUNNING:
        return

    _SUMMARY_RUNNING.add(user_id)
    try:
        snapshot = list(history)
        lines = []
        for role, content in snapshot:
            tag = "کاربر" if role == "user" else "دستیار"
            lines.append(f"{tag}: {content[:500]}")
        blob = "\n".join(lines)[:5000]
        summary_prompt = (
            "این گفتگو را در حداکثر ۸ خط فارسی خلاصه کن. "
            "حقایق مهم درباره کاربر، تصمیم‌ها و موضوعات اصلی را نگه دار:\n\n" + blob
        )

        summary = None
        for provider, _label, model in available_model_options():
            try:
                if provider == "groq":
                    summary = await _openai_compatible(
                        "Groq", "groq", 0, summary_prompt,
                        url=os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1").rstrip("/")
                        + "/chat/completions",
                        model=model,
                        use_tools=False,
                    )
                elif provider == "gemini":
                    summary = await _gemini(0, summary_prompt, model, use_tools=False)
                else:
                    continue
                if summary:
                    break
            except Exception:
                continue

        if summary:
            from bot.database import get_ai_history_summary, set_ai_history_summary
            prev = get_ai_history_summary(user_id) or ""
            merged = (prev + "\n" + summary).strip() if prev else summary
            set_ai_history_summary(user_id, merged[-3500:])

            # نصف جدیدتر تاریخچه را نگه می‌داریم.
            keep = max(2, HISTORY_ITEMS // 2)
            while len(history) > keep:
                history.popleft()
    except Exception as e:
        logger.warning("auto summarize failed: %s", e)
    finally:
        _SUMMARY_RUNNING.discard(user_id)


def _messages(user_id: int, prompt: str) -> List[dict]:
    system = SYSTEM_PROMPT
    mem = _memory_block(user_id)
    if mem:
        system = system + "\n\n" + mem
    messages = [{"role": "system", "content": system}]
    for role, content in _HISTORY[user_id]:
        messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": prompt})
    return messages


def _save_turn(user_id: int, prompt: str, answer: str) -> None:
    history = _HISTORY[user_id]
    history.append(("user", prompt))
    history.append(("assistant", answer))
    # خلاصه‌سازی در پس‌زمینه وقتی پر شد
    if len(history) >= HISTORY_ITEMS:
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(_maybe_summarize_history(user_id))
        except Exception:
            pass


async def _post_json(url: str, *, headers=None, json=None, params=None) -> tuple[int, dict]:
    client = _get_http()
    response = await client.post(url, headers=headers, json=json, params=params)
    try:
        data = response.json()
    except Exception:
        data = {"raw": response.text[:1200]}
    return response.status_code, data


def _extract_openai(data: dict) -> str:
    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError(str(data)[:900])

    message = choices[0].get("message") or {}
    content = message.get("content")

    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                text = item.get("text")
                if text:
                    parts.append(str(text))
        content = "".join(parts)

    if not content:
        raise RuntimeError("Provider returned an empty answer")

    return str(content).strip()


# ── Provider callers with key rotation ──────────────────────────────────────

async def _gemini(
    user_id: int,
    prompt: str,
    model: str,
    *,
    use_tools: bool = True,
    max_tool_rounds: int = 2,
) -> str:
    """
    Gemini REST caller with real function-calling support.

    نسخه قبلی فقط برای Gemini از keyword injection استفاده می‌کرد، در حالی که
    registry ابزارها برای OpenAI-compatibleها واقعاً اجرا می‌شد. این نسخه هر دو
    مسیر را دارد: function calling واقعی + دادهٔ زندهٔ keyword-based به‌عنوان fallback.
    """
    keys = _next_keys("gemini")
    if not keys:
        raise RuntimeError("هیچ کلید Gemini تنظیم نشده")

    from bot.services.ai_tools import get_tool_definitions, execute_tool, parse_tool_arguments

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

    contents = []
    for role, content in _HISTORY[user_id]:
        contents.append({
            "role": "model" if role == "assistant" else "user",
            "parts": [{"text": content}],
        })
    contents.append({"role": "user", "parts": [{"text": prompt}]})

    # OpenAI-style registry -> Gemini functionDeclarations
    gemini_tools = []
    if use_tools:
        declarations = []
        for tool in get_tool_definitions():
            fn = tool.get("function") or {}
            if fn.get("name"):
                declarations.append({
                    "name": fn["name"],
                    "description": fn.get("description", ""),
                    "parameters": fn.get(
                        "parameters",
                        {"type": "object", "properties": {}},
                    ),
                })
        if declarations:
            gemini_tools = [{"functionDeclarations": declarations}]

    errors = []
    for key in keys:
        try:
            working_contents = list(contents)

            for _round in range(max_tool_rounds + 1 if use_tools else 1):
                payload = {
                    "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT + (("\n\n" + _memory_block(user_id)) if _memory_block(user_id) else "")}]},
                    "contents": working_contents,
                    "generationConfig": {"maxOutputTokens": MAX_OUTPUT},
                }
                if gemini_tools and _round < max_tool_rounds:
                    payload["tools"] = gemini_tools

                status, data = await _post_json(
                    url, params={"key": key}, json=payload
                )

                if status >= 400:
                    if _is_quota_error(status, data):
                        text = str(data).lower()
                        daily = status == 403 or "daily" in text or "quota" in text
                        _mark_key_cooldown("gemini", key, daily=daily)
                        errors.append(f"{_key_id('gemini', key)} HTTP {status}")
                        break
                    raise RuntimeError(
                        f"Gemini HTTP {status}: {str(data)[:900]}"
                    )

                candidates = data.get("candidates") or []
                if not candidates:
                    raise RuntimeError(
                        f"Gemini پاسخ خالی داد: {str(data)[:900]}"
                    )

                content = candidates[0].get("content") or {}
                parts = content.get("parts") or []

                function_calls = [
                    p.get("functionCall") or p.get("function_call")
                    for p in parts
                    if p.get("functionCall") or p.get("function_call")
                ]

                if function_calls and use_tools and _round < max_tool_rounds:
                    # پاسخ مدل را عیناً به history موقت اضافه کن.
                    working_contents.append({
                        "role": "model",
                        "parts": parts,
                    })

                    response_parts = []
                    for call in function_calls:
                        name = call.get("name") or ""
                        args = call.get("args") or call.get("arguments") or {}
                        args = parse_tool_arguments(args)
                        result = await execute_tool(
                            name, args, user_id=user_id
                        )
                        response_parts.append({
                            "functionResponse": {
                                "name": name,
                                "response": {"result": result},
                            }
                        })

                    if response_parts:
                        working_contents.append({
                            "role": "user",
                            "parts": response_parts,
                        })
                        continue

                text = "".join(
                    p.get("text", "")
                    for p in parts
                    if isinstance(p, dict)
                ).strip()

                if not text:
                    raise RuntimeError(
                        f"Gemini پاسخ متنی خالی داد: {str(data)[:700]}"
                    )

                _advance_rr("gemini")
                return text

        except RuntimeError as exc:
            errors.append(str(exc)[:300])
            continue
        except Exception as exc:
            errors.append(str(exc)[:300])
            continue

    raise RuntimeError(
        "همه کلیدهای Gemini تمام/خطا: " + " | ".join(errors[:5])
    )


async def _openai_compatible(
    name: str,
    provider: str,
    user_id: int,
    prompt: str,
    *,
    url: str,
    model: str,
    extra_headers=None,
    use_tools: bool = True,
) -> str:
    from bot.services.ai_tools import (
        get_tool_definitions,
        execute_tool,
        parse_tool_arguments,
    )

    keys = _next_keys(provider)
    if not keys:
        raise RuntimeError(f"هیچ کلید {name} تنظیم نشده")

    errors = []
    for key in keys:
        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }
        if extra_headers:
            headers.update(extra_headers)

        messages = _messages(user_id, prompt)
        # حداکثر ۲ دور tool calling تا گیر نکند
        max_tool_rounds = 2 if use_tools else 0
        tools_enabled = bool(use_tools)

        try:
            for _round in range(max_tool_rounds + 1):
                payload = {
                    "model": model,
                    "messages": messages,
                    "max_tokens": MAX_OUTPUT,
                    "temperature": 0.6,
                }
                if tools_enabled and _round < max_tool_rounds:
                    tools = get_tool_definitions()
                    if tools:
                        payload["tools"] = tools
                        payload["tool_choice"] = "auto"

                status, data = await _post_json(url, headers=headers, json=payload)
                if status >= 400:
                    # بعضی مدل‌ها tools را پشتیبانی نمی‌کنند → بدون tool دوباره امتحان
                    err_text = str(data).lower()
                    if tools_enabled and (
                        "tool" in err_text
                        or "function" in err_text
                        or status in (400, 422)
                    ):
                        tools_enabled = False
                        payload.pop("tools", None)
                        payload.pop("tool_choice", None)
                        try:
                            from bot.services.ai_tools import gather_context_for_prompt
                            extra = await gather_context_for_prompt(user_id, prompt)
                            if extra:
                                fallback_messages = _messages(user_id, prompt)
                                fallback_messages[-1]["content"] = (prompt + extra)[:MAX_INPUT]
                                payload["messages"] = fallback_messages
                        except Exception:
                            pass
                        status, data = await _post_json(
                            url, headers=headers, json=payload
                        )
                    if status >= 400:
                        if _is_quota_error(status, data):
                            daily = (
                                "daily" in str(data).lower()
                                or "quota" in str(data).lower()
                                or status == 403
                            )
                            _mark_key_cooldown(
                                provider, key, daily=daily or status == 429
                            )
                            errors.append(f"{_key_id(provider, key)} HTTP {status}")
                            break
                        raise RuntimeError(
                            f"{name} HTTP {status}: {str(data)[:900]}"
                        )

                choices = data.get("choices") or []
                if not choices:
                    raise RuntimeError(str(data)[:900])

                message = choices[0].get("message") or {}
                tool_calls = message.get("tool_calls") or []

                if tool_calls and tools_enabled:
                    # پاسخ assistant با tool_calls را به تاریخچه اضافه کن
                    messages.append(message)
                    for tc in tool_calls:
                        fn = tc.get("function") or {}
                        fname = fn.get("name") or ""
                        fargs = parse_tool_arguments(fn.get("arguments"))
                        result = await execute_tool(
                            fname, fargs, user_id=user_id
                        )
                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": tc.get("id") or fname,
                                "content": result,
                            }
                        )
                    continue  # دور بعد با نتایج tool

                text = _extract_openai(data)
                _advance_rr(provider)
                return text

            # اگر از حلقه key بیرون آمدیم بدون return
            continue
        except RuntimeError as exc:
            msg = str(exc)
            if _is_quota_error(0, msg) or "429" in msg or "403" in msg:
                _mark_key_cooldown(provider, key, daily=True)
            errors.append(msg[:200])
            continue

    raise RuntimeError(f"همه کلیدهای {name} تمام/خطا: " + " | ".join(errors[:5]))


async def _groq(user_id: int, prompt: str, model: str) -> str:
    return await _openai_compatible(
        "Groq",
        "groq",
        user_id,
        prompt,
        url=os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1").rstrip("/")
        + "/chat/completions",
        model=model,
    )


async def _cerebras(user_id: int, prompt: str, model: str) -> str:
    return await _openai_compatible(
        "Cerebras",
        "cerebras",
        user_id,
        prompt,
        url="https://api.cerebras.ai/v1/chat/completions",
        model=model,
    )


async def _openrouter(user_id: int, prompt: str, model: str) -> str:
    return await _openai_compatible(
        "OpenRouter",
        "openrouter",
        user_id,
        prompt,
        url="https://openrouter.ai/api/v1/chat/completions",
        model=model,
        extra_headers={"X-Title": "Rooze Ziba"},
    )


async def _cloudflare(user_id: int, prompt: str, model: str) -> str:
    # Cloudflare AI Run does not expose the same OpenAI tool-call contract here.
    # For live-data questions, prefetch only matching keyword tools.
    try:
        from bot.services.ai_tools import prompt_has_keyword_tool, gather_context_for_prompt
        if prompt_has_keyword_tool(prompt):
            extra = await gather_context_for_prompt(user_id, prompt)
            if extra:
                prompt = (prompt + extra)[:MAX_INPUT]
    except Exception as exc:
        logger.warning("Cloudflare tool fallback failed: %s", exc)
    account = os.getenv("CLOUDFLARE_ACCOUNT_ID")
    if not account:
        raise RuntimeError("CLOUDFLARE_ACCOUNT_ID تنظیم نشده")
    keys = _next_keys("cloudflare")
    if not keys:
        raise RuntimeError("هیچ توکن Cloudflare تنظیم نشده")

    url = f"https://api.cloudflare.com/client/v4/accounts/{account}/ai/run/{model}"
    payload = {
        "messages": _messages(user_id, prompt),
        "max_tokens": MAX_OUTPUT,
    }

    errors = []
    for token in keys:
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        try:
            status, data = await _post_json(url, headers=headers, json=payload)
            if status >= 400 or not data.get("success", True):
                if _is_quota_error(status, data):
                    _mark_key_cooldown("cloudflare", token, daily=True)
                    errors.append(f"{_key_id('cloudflare', token)} HTTP {status}")
                    continue
                raise RuntimeError(f"Cloudflare HTTP {status}: {str(data)[:900]}")

            result = data.get("result") or {}
            text = result.get("response") or result.get("text")
            if not text:
                raise RuntimeError(f"Cloudflare empty response: {str(data)[:900]}")
            _advance_rr("cloudflare")
            return str(text).strip()
        except RuntimeError as exc:
            errors.append(str(exc)[:200])
            continue

    raise RuntimeError("همه توکن‌های Cloudflare تمام/خطا: " + " | ".join(errors[:5]))


async def _call_provider(provider: str, user_id: int, prompt: str, model: str) -> str:
    if provider == "gemini":
        return await _gemini(user_id, prompt, model)
    if provider == "groq":
        return await _groq(user_id, prompt, model)
    if provider == "cerebras":
        return await _cerebras(user_id, prompt, model)
    if provider == "cloudflare":
        return await _cloudflare(user_id, prompt, model)
    if provider == "openrouter":
        return await _openrouter(user_id, prompt, model)
    raise RuntimeError(f"Unknown AI provider: {provider}")



async def _gemini_with_media(
    user_id: int,
    prompt: str,
    model: str,
    media: list[tuple[bytes, str]] | None = None,
) -> str:
    """Gemini multimodal: متن + عکس (و در صورت نیاز چند فایل تصویری)."""
    keys = _next_keys("gemini")
    if not keys:
        raise RuntimeError("هیچ کلید Gemini تنظیم نشده")

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    contents = []
    for role, content in _HISTORY[user_id]:
        contents.append(
            {
                "role": "model" if role == "assistant" else "user",
                "parts": [{"text": content}],
            }
        )

    parts = []
    if media:
        for data, mime in media:
            # محدودیت اندازه ~4MB برای inline
            if len(data) > 4_500_000:
                raise RuntimeError("حجم فایل برای تحلیل خیلی بزرگ است (حداکثر حدود ۴ مگابایت).")
            parts.append(
                {
                    "inline_data": {
                        "mime_type": mime or "image/jpeg",
                        "data": base64.b64encode(data).decode("ascii"),
                    }
                }
            )
    parts.append({"text": prompt})
    contents.append({"role": "user", "parts": parts})

    payload = {
        "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": contents,
        "generationConfig": {"maxOutputTokens": MAX_OUTPUT},
    }

    errors = []
    for key in keys:
        try:
            status, data = await _post_json(url, params={"key": key}, json=payload)
            if status >= 400:
                if _is_quota_error(status, data):
                    daily = status != 429 or "daily" in str(data).lower() or "quota" in str(data).lower()
                    _mark_key_cooldown("gemini", key, daily=daily)
                    errors.append(f"{_key_id('gemini', key)} HTTP {status}")
                    continue
                raise RuntimeError(f"Gemini HTTP {status}: {str(data)[:900]}")

            try:
                parts_out = data["candidates"][0]["content"]["parts"]
                text = "".join(p.get("text", "") for p in parts_out).strip()
            except Exception:
                raise RuntimeError(f"Gemini unexpected response: {str(data)[:900]}")

            if not text:
                raise RuntimeError("Gemini returned an empty answer")

            _advance_rr("gemini")
            return text
        except RuntimeError as exc:
            if "HTTP" in str(exc) and any(x in str(exc) for x in ("429", "403", "quota")):
                _mark_key_cooldown("gemini", key, daily=True)
                errors.append(str(exc)[:200])
                continue
            errors.append(str(exc)[:200])
            continue

    raise RuntimeError("همه کلیدهای Gemini تمام/خطا: " + " | ".join(errors[:5]))


def _extract_text_from_bytes(data: bytes, filename: str = "", mime: str = "") -> str:
    """استخراج متن از فایل‌های متنی/PDF ساده."""
    name = (filename or "").lower()
    mime = (mime or "").lower()

    # متن ساده
    if (
        mime.startswith("text/")
        or name.endswith((".txt", ".md", ".csv", ".json", ".py", ".js", ".html", ".xml", ".log"))
    ):
        for enc in ("utf-8", "utf-8-sig", "cp1256", "latin-1"):
            try:
                return data.decode(enc)
            except Exception:
                continue
        return data.decode("utf-8", errors="replace")

    # PDF
    if mime == "application/pdf" or name.endswith(".pdf"):
        try:
            from pypdf import PdfReader  # optional
            import io

            reader = PdfReader(io.BytesIO(data))
            pages = []
            for i, page in enumerate(reader.pages[:30]):
                t = page.extract_text() or ""
                if t.strip():
                    pages.append(f"--- صفحه {i+1} ---\n{t}")
            if pages:
                return "\n\n".join(pages)
        except Exception as e:
            logger.warning("pdf extract failed: %s", e)
            return (
                "نتوانستم متن PDF را استخراج کنم. "
                "اگر pypdf نصب باشد یا فایل متنی بفرستی بهتر کار می‌کند."
            )

    # docx
    if name.endswith(".docx") or "wordprocessingml" in mime:
        try:
            import zipfile
            import io
            import re as _re

            with zipfile.ZipFile(io.BytesIO(data)) as z:
                xml = z.read("word/document.xml").decode("utf-8", errors="ignore")
            texts = _re.findall(r"<w:t[^>]*>(.*?)</w:t>", xml)
            return "\n".join(texts) if texts else "متن قابل استخراج از docx نبود."
        except Exception as e:
            logger.warning("docx extract failed: %s", e)
            return "خطا در خواندن فایل Word."

    return ""


async def ask_ai_media(
    user_id: int,
    prompt: str,
    *,
    images: list[tuple[bytes, str]] | None = None,
    file_text: str | None = None,
    filename: str = "",
) -> tuple[str, str]:
    """
    تحلیل عکس و/یا محتوای فایل با AI.
    images: لیست (bytes, mime_type)
    file_text: متن استخراج‌شده از فایل
    """
    prompt = (prompt or "").strip()
    images = images or []

    parts_desc = []
    if images:
        parts_desc.append(f"{len(images)} تصویر")
    if file_text:
        parts_desc.append(f"فایل متنی{(' ' + filename) if filename else ''}")

    if not prompt:
        if images and not file_text:
            prompt = "این تصویر را کامل و دقیق تحلیل کن. محتوا، متن داخل عکس، اشیاء و هر نکته مهم را بگو."
        elif file_text and not images:
            prompt = "محتوای این فایل را کامل بررسی و خلاصهٔ مفید + نکات مهم بده."
        else:
            prompt = "این ورودی را کامل تحلیل کن."

    # متن فایل را به پرامپت بچسبان
    if file_text:
        clipped = file_text[:12000]
        prompt = (
            f"{prompt}\n\n"
            f"[محتوای فایل{(' : ' + filename) if filename else ''}]\n{clipped}"
        )

    if len(prompt) > MAX_INPUT:
        prompt = prompt[:MAX_INPUT]

    options = available_model_options()
    if not options:
        raise RuntimeError("هیچ سرویس AI تنظیم نشده است.")

    original_prompt = prompt if not file_text else (prompt.split("[محتوای فایل")[0].strip() or "تحلیل فایل")

    async with _LOCKS[user_id]:
        selected = get_selected_model(user_id)
        errors: list[str] = []

        # برای تصویر: اولویت با Gemini (بینایی)
        ordered_providers: list[str] = []
        if images:
            ordered_providers.append("gemini")
        if selected:
            p = selected[0]
            if p not in ordered_providers:
                ordered_providers.insert(0, p)
        for p, _l, _m in options:
            if p not in ordered_providers:
                ordered_providers.append(p)

        for provider in ordered_providers:
            models = models_for_provider(provider)
            if not models:
                continue
            for model in models:
                try:
                    if images and provider == "gemini":
                        answer = await _gemini_with_media(
                            user_id, prompt, model, media=images
                        )
                    elif images and provider != "gemini":
                        # مدل‌های بدون بینایی: توضیح بده که تصویر را نمی‌بینند
                        # ولی اگر متن فایل هم هست همان را جواب بدهند
                        if not file_text:
                            raise RuntimeError(
                                f"{provider} از تحلیل تصویر پشتیبانی نمی‌کند؛ Gemini را انتخاب کن."
                            )
                        answer = await _call_provider(provider, user_id, prompt, model)
                    else:
                        answer = await _call_provider(provider, user_id, prompt, model)

                    _save_turn(user_id, original_prompt[:500], answer)
                    if not selected:
                        set_selected_model(user_id, provider, "*")
                    return answer, f"{provider} / {model}"
                except Exception as exc:
                    msg = str(exc).replace("\n", " ")[:400]
                    errors.append(f"{provider}/{model}: {msg}")
                    logger.warning("ask_ai_media failed: %s", msg)
                    await asyncio.sleep(0.05)

    raise RuntimeError(
        "نتوانستم عکس/فایل را تحلیل کنم.\n\n" + "\n".join(errors[:8])
    )



# ── ساخت / ویرایش تصویر با Gemini (Nano Banana) ─────────────────────────────

IMAGE_GEN_MODEL = os.getenv(
    "GEMINI_IMAGE_MODEL",
    "gemini-3.1-flash-image",
)


async def generate_or_edit_image(
    prompt: str,
    *,
    source_image: bytes | None = None,
    source_mime: str = "image/jpeg",
) -> tuple[bytes, str]:
    """
    ساخت تصویر از متن، یا ویرایش تصویر با دستور متنی.
    خروجی: (image_bytes, mime_type)
    نیاز به کلید Gemini دارد.
    """
    prompt = (prompt or "").strip()
    if not prompt:
        raise RuntimeError("توضیح تصویر خالی است.")

    keys = _next_keys("gemini")
    if not keys:
        raise RuntimeError("برای ساخت/ویرایش تصویر به کلید Gemini نیاز است.")

    model = IMAGE_GEN_MODEL
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

    parts = []
    if source_image:
        if len(source_image) > 4_500_000:
            raise RuntimeError("حجم تصویر برای ویرایش خیلی بزرگ است.")
        parts.append(
            {
                "inline_data": {
                    "mime_type": source_mime or "image/jpeg",
                    "data": base64.b64encode(source_image).decode("ascii"),
                }
            }
        )
        full_prompt = (
            "Edit this image according to the following instruction. "
            "Return the edited image.\n\n" + prompt
        )
    else:
        full_prompt = (
            "Generate a high-quality image for this request. "
            "Return an image.\n\n" + prompt
        )
    parts.append({"text": full_prompt})

    payload = {
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": {
            "responseModalities": ["TEXT", "IMAGE"],
        },
    }

    errors = []
    for key in keys:
        try:
            status, data = await _post_json(url, params={"key": key}, json=payload)
            if status >= 400:
                if _is_quota_error(status, data):
                    _mark_key_cooldown("gemini", key, daily=True)
                    errors.append(f"{_key_id('gemini', key)} HTTP {status}")
                    continue
                # fallback مدل قدیمی‌تر
                if "not found" in str(data).lower() or status == 404:
                    alt = os.getenv("GEMINI_IMAGE_MODEL_FALLBACK", "gemini-2.5-flash-image")
                    if model != alt:
                        model = alt
                        url = (
                            f"https://generativelanguage.googleapis.com/v1beta/models/"
                            f"{model}:generateContent"
                        )
                        status, data = await _post_json(
                            url, params={"key": key}, json=payload
                        )
                        if status >= 400:
                            raise RuntimeError(
                                f"Gemini image HTTP {status}: {str(data)[:700]}"
                            )
                    else:
                        raise RuntimeError(
                            f"Gemini image HTTP {status}: {str(data)[:700]}"
                        )
                else:
                    raise RuntimeError(
                        f"Gemini image HTTP {status}: {str(data)[:700]}"
                    )

            candidates = data.get("candidates") or []
            if not candidates:
                raise RuntimeError(f"پاسخ خالی از مدل تصویر: {str(data)[:500]}")

            out_parts = (candidates[0].get("content") or {}).get("parts") or []
            text_bits = []
            image_bytes = None
            mime = "image/png"
            for part in out_parts:
                if "text" in part and part["text"]:
                    text_bits.append(part["text"])
                inline = part.get("inlineData") or part.get("inline_data")
                if inline and inline.get("data"):
                    image_bytes = base64.b64decode(inline["data"])
                    mime = inline.get("mimeType") or inline.get("mime_type") or "image/png"

            if not image_bytes:
                msg = " ".join(text_bits)[:500] or str(data)[:500]
                raise RuntimeError(
                    "مدل تصویری برنگرداند. ممکن است این مدل در کلید شما فعال نباشد یا محدودیت داشته باشد.\n"
                    + msg
                )

            _advance_rr("gemini")
            return image_bytes, mime
        except RuntimeError as exc:
            errors.append(str(exc)[:250])
            continue

    raise RuntimeError(
        "ساخت/ویرایش تصویر ناموفق بود.\n" + " | ".join(errors[:5])
    )


def looks_like_image_request(text: str) -> bool:
    """آیا پیام درخواست ساخت تصویر است؟"""
    t = (text or "").strip()
    if not t:
        return False
    patterns = (
        r"تصویر\s*بساز",
        r"عکس\s*بساز",
        r"عکس\s*تولید",
        r"تصویر\s*تولید",
        r"بکش",
        r"نقاشی\s*کن",
        r"generate\s+(an?\s+)?image",
        r"draw\s+(me\s+)?",
        r"create\s+(an?\s+)?image",
        r"image\s+of",
        r"طراحی\s*کن",
        r"پرامپت\s*تصویر",
    )
    import re
    return any(re.search(p, t, re.I) for p in patterns)


def looks_like_image_edit(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    patterns = (
        r"ویرایش",
        r"تغییر\s*بده",
        r"عوض\s*کن",
        r"اضافه\s*کن",
        r"حذف\s*کن",
        r"edit\s+(this\s+)?image",
        r"change\s+",
        r"remove\s+",
        r"add\s+",
        r"بدل\s*کن",
        r"سبک\s*",
    )
    import re
    return any(re.search(p, t, re.I) for p in patterns)



# ── تبدیل متن به ویس (TTS) ─────────────────────────────────────────────────

TTS_VOICE = os.getenv("TTS_VOICE", "fa-IR-DilaraNeural")  # فارسی زن
# جایگزین‌ها: fa-IR-FaridNeural (مرد)



# ── ویس → متن (Speech-to-Text) ─────────────────────────────────────────────

async def speech_to_text(
    audio_bytes: bytes,
    *,
    filename: str = "voice.ogg",
    mime: str = "audio/ogg",
) -> str:
    """
    تبدیل ویس/صوت به متن.
    اولویت: Groq Whisper → سپس Gemini.
    """
    if not audio_bytes:
        raise RuntimeError("فایل صوتی خالی است.")

    errors = []

    # ۱) Groq Whisper (سریع و معمولاً رایگان در سهمیه)
    groq_keys = _next_keys("groq")
    if groq_keys:
        import httpx as _httpx

        for key in groq_keys:
            try:
                url = (
                    os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1").rstrip("/")
                    + "/audio/transcriptions"
                )
                model = os.getenv("GROQ_STT_MODEL", "whisper-large-v3-turbo")
                files = {
                    "file": (filename or "audio.ogg", audio_bytes, mime or "audio/ogg"),
                }
                data = {
                    "model": model,
                    "language": os.getenv("STT_LANGUAGE", "fa"),  # فارسی
                    "response_format": "text",
                }
                headers = {"Authorization": f"Bearer {key}"}
                async with _httpx.AsyncClient(timeout=60.0) as client:
                    resp = await client.post(
                        url, headers=headers, data=data, files=files
                    )
                if resp.status_code >= 400:
                    if _is_quota_error(resp.status_code, resp.text):
                        _mark_key_cooldown("groq", key, daily=True)
                        errors.append(f"groq STT HTTP {resp.status_code}")
                        continue
                    errors.append(f"groq STT HTTP {resp.status_code}: {resp.text[:200]}")
                    continue
                text = (resp.text or "").strip()
                # گاهی JSON برمی‌گردد
                if text.startswith("{"):
                    try:
                        import json as _json
                        text = (_json.loads(text).get("text") or "").strip()
                    except Exception:
                        pass
                if text:
                    _advance_rr("groq")
                    return text
                errors.append("groq STT empty")
            except Exception as e:
                errors.append(f"groq STT: {e}")
                continue

    # ۲) Gemini (ورودی audio)
    gemini_keys = _next_keys("gemini")
    if gemini_keys:
        model = os.getenv("GEMINI_STT_MODEL", "gemini-3.5-flash-lite")
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:generateContent"
        )
        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {
                            "inline_data": {
                                "mime_type": mime or "audio/ogg",
                                "data": base64.b64encode(audio_bytes).decode("ascii"),
                            }
                        },
                        {
                            "text": (
                                "این فایل صوتی را دقیقاً به متن پیاده کن. "
                                "فقط متن گفتار را برگردان، بدون توضیح اضافه."
                            )
                        },
                    ],
                }
            ],
            "generationConfig": {"maxOutputTokens": 2048},
        }
        for key in gemini_keys:
            try:
                status, data = await _post_json(url, params={"key": key}, json=payload)
                if status >= 400:
                    if _is_quota_error(status, data):
                        _mark_key_cooldown("gemini", key, daily=True)
                    errors.append(f"gemini STT HTTP {status}")
                    continue
                parts = data["candidates"][0]["content"]["parts"]
                text = "".join(p.get("text", "") for p in parts).strip()
                if text:
                    _advance_rr("gemini")
                    return text
                errors.append("gemini STT empty")
            except Exception as e:
                errors.append(f"gemini STT: {e}")
                continue

    raise RuntimeError(
        "نتوانستم ویس را به متن تبدیل کنم. کلید Groq یا Gemini لازم است.\n"
        + " | ".join(errors[:5])
    )



async def analyze_voice_emotion(
    audio_bytes: bytes,
    *,
    transcript: str = "",
    filename: str = "voice.ogg",
    mime: str = "audio/ogg",
) -> str:
    """
    تشخیص احساسات و لحن از روی صدا (و در صورت وجود متن پیاده‌شده).
    با Gemini روی خود فایل صوتی کار می‌کند.
    """
    if not audio_bytes:
        raise RuntimeError("فایل صوتی خالی است.")

    keys = _next_keys("gemini")
    if not keys:
        # بدون Gemini: تخمین ضعیف از روی متن
        if transcript:
            return _emotion_from_text_fallback(transcript)
        raise RuntimeError("برای تشخیص احساس از صدا به کلید Gemini نیاز است.")

    if len(audio_bytes) > 4_500_000:
        audio_bytes = audio_bytes[:4_500_000]

    model = os.getenv("GEMINI_EMOTION_MODEL", os.getenv("GEMINI_STT_MODEL", "gemini-3.5-flash-lite"))
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

    prompt = (
        "تو یک تحلیل‌گر لحن و احساس صدا هستی. این فایل صوتی را گوش بده "
        "(و اگر متن پیاده‌شده آمد از آن هم کمک بگیر) و به فارسی پاسخ بده.\n\n"
        "ساختار پاسخ دقیقاً این باشد:\n"
        "😊 احساس غالب: ...\n"
        "📊 شدت (۰ تا ۱۰): ...\n"
        "🎙 لحن/انرژی: ...\n"
        "💬 احساسات فرعی: ...\n"
        "📝 توضیح کوتاه: ...\n\n"
        "احساسات ممکن: شادی، غم، عصبانیت، اضطراب، آرامش، هیجان، خستگی، "
        "اعتمادبه‌نفس، تردید، مهربانی، بی‌حوصلگی، ترس، تعجب.\n"
        "اگر صدا واضح نبود صادقانه بگو."
    )
    if transcript:
        prompt += f"\n\nمتن پیاده‌شده از صدا:\n{transcript[:1500]}"

    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {
                        "inline_data": {
                            "mime_type": mime or "audio/ogg",
                            "data": base64.b64encode(audio_bytes).decode("ascii"),
                        }
                    },
                    {"text": prompt},
                ],
            }
        ],
        "generationConfig": {"maxOutputTokens": 800},
    }

    errors = []
    for key in keys:
        try:
            status, data = await _post_json(url, params={"key": key}, json=payload)
            if status >= 400:
                if _is_quota_error(status, data):
                    _mark_key_cooldown("gemini", key, daily=True)
                    errors.append(f"HTTP {status}")
                    continue
                raise RuntimeError(f"Gemini emotion HTTP {status}: {str(data)[:400]}")
            parts = data["candidates"][0]["content"]["parts"]
            text = "".join(x.get("text", "") for x in parts).strip()
            if text:
                _advance_rr("gemini")
                return text
            errors.append("empty")
        except Exception as e:
            errors.append(str(e)[:200])
            continue

    if transcript:
        return _emotion_from_text_fallback(transcript)
    raise RuntimeError("تشخیص احساس ناموفق: " + " | ".join(errors[:4]))


def _emotion_from_text_fallback(transcript: str) -> str:
    """تخمین خیلی ساده فقط از روی واژه‌ها (وقتی Gemini نباشد)."""
    t = (transcript or "").lower()
    rules = [
        (["عصبانی", "خفه", "لعنت", "حالم بده از", "کیفم کوک نیست"], "عصبانیت"),
        (["میترسم", "نگران", "استرس", "دلهره"], "اضطراب/نگرانی"),
        (["خوشحالم", "عالی", "محشر", "عاشق", "خنده‌ام"], "شادی"),
        (["غمگین", "گریه", "دلتنگ", "تنها", "سخت"], "غم"),
        (["خسته‌ام", "حالم نیست", "بی‌حال"], "خستگی"),
        (["آروم", "خوبه", "ممنون", "مرسی"], "آرامش"),
    ]
    found = []
    for words, label in rules:
        if any(w in t for w in words):
            found.append(label)
    if not found:
        found = ["خنثی / نامشخص از روی متن"]
    return (
        "😊 احساس غالب (تخمین از متن، نه صدا): "
        + "، ".join(found)
        + "\n📝 برای تشخیص دقیق از لحن صدا، کلید Gemini لازم است."
    )


async def text_to_speech(text: str, *, voice: str | None = None) -> bytes:
    """
    متن → فایل صوتی ogg/mp3 (edge-tts، بدون نیاز به API Key).
    خروجی bytes مناسب ارسال با reply_voice در تلگرام.
    """
    text = (text or "").strip()
    if not text:
        raise RuntimeError("متن خالی است.")
    # تلگرام برای voice محدودیت حدود ۱ دقیقه دارد؛ متن را کمی محدود کن
    if len(text) > 1200:
        text = text[:1200] + " …"

    voice = voice or TTS_VOICE
    try:
        import edge_tts
        import tempfile
        from pathlib import Path as _P

        communicate = edge_tts.Communicate(text, voice)
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            tmp = f.name
        await communicate.save(tmp)
        data = _P(tmp).read_bytes()
        try:
            _P(tmp).unlink(missing_ok=True)
        except Exception:
            pass
        if not data:
            raise RuntimeError("فایل صوتی خالی بود.")
        return data
    except ImportError:
        raise RuntimeError(
            "کتابخانه edge-tts نصب نیست. در requirements.txt بنویس: edge-tts"
        )
    except Exception as e:
        raise RuntimeError(f"ساخت ویس ناموفق: {e}")




def wants_emotion_analysis(text: str) -> bool:
    """آیا کاربر صریحاً تشخیص احساس از صدا خواسته؟"""
    t = (text or "").strip()
    if not t:
        return False
    import re
    patterns = (
        r"تشخیص\s*احساس",
        r"احساس(ات)?\s*(من|صدا|از\s*صدا)?",
        r"لحن(م|م\s*چطور)",
        r"از\s*صدا(م)?\s*(بگو|تحلیل|تشخیص)",
        r"حالم\s*از\s*صدا",
        r"emotion",
        r"تحلیل\s*احساس",
        r"چه\s*احساسی",
    )
    return any(re.search(p, t, re.I) for p in patterns)


def wants_voice_chat_mode(text: str) -> bool:
    """درخواست شروع مکالمه ویسی پایدار (نه فقط یک‌بار)."""
    t = (text or "").strip()
    if not t:
        return False
    import re
    patterns = (
        r"ویس\s*حرف\s*بزن",
        r"با\s*ویس\s*حرف",
        r"حرف\s*بزنیم\s*(با\s*)?ویس",
        r"صحبت\s*(صوتی|ویسی|با\s*صدا)",
        r"چت\s*صوتی",
        r"مکالمه\s*(ی\s*)?(صوتی|ویسی)",
        r"از\s*این\s*به\s*بعد\s*(با\s*)?(ویس|صدا)",
        r"فقط\s*ویس",
        r"voice\s*chat",
        r"let'?s\s*talk\s*(by\s*)?voice",
        r"با\s*صدا\s*حرف",
        r"صدا\s*حرف\s*بزن",
        r"بیا\s*ویس",
        r"ویس\s*باش",
        r"حالت\s*ویس",
        r"حالت\s*صوتی",
    )
    return any(re.search(p, t, re.I) for p in patterns)


def wants_end_voice_chat(text: str) -> bool:
    """پایان حالت مکالمه ویسی."""
    t = (text or "").strip()
    if not t:
        return False
    import re
    patterns = (
        r"قطع\s*ویس",
        r"بدون\s*ویس",
        r"دیگه\s*ویس\s*ن",
        r"متن(ی)?\s*حرف\s*بزن",
        r"حالت\s*متنی",
        r"ویس\s*رو\s*خاموش",
        r"خاموش\s*کردن\s*ویس",
        r"end\s*voice",
        r"stop\s*voice",
        r"فقط\s*متن",
    )
    return any(re.search(p, t, re.I) for p in patterns)


def wants_voice_reply(text: str) -> bool:
    """درخواست صریح ویس برای همین پیام."""
    t = (text or "").strip()
    if not t:
        return False
    import re
    if wants_voice_chat_mode(t):
        return True
    patterns = (
        r"^با\s*ویس\b",
        r"^با\s*صدا\b",
        r"^ویس\s*[:：]",
        r"^صدا\s*[:：]",
        r"ویس\s*بفرست",
        r"صدا\s*بفرست",
        r"بفرست\s*ویس",
        r"بفرست\s*صدا",
        r"فایل\s*صوتی",
        r"صوتی\s*بفرست",
        r"\bبا\s*ویس\s*بگو\b",
        r"\bبا\s*صدا\s*بگو\b",
        r"\bجواب(تو)?\s*(رو\s*)?با\s*ویس\b",
        r"\bجواب(تو)?\s*(رو\s*)?با\s*صدا\b",
        r"\bبرام\s*بخون\b",
        r"\bspeak\b",
        r"\bvoice\s*reply\b",
        r"\btts\b",
        r"send\s*(a\s*)?voice",
    )
    return any(re.search(p, t, re.I) for p in patterns)


def is_voice_only_request(text: str) -> bool:
    """فقط درخواست ویس بدون سؤال دیگر (مثل: ویس بفرست)."""
    t = (text or "").strip()
    if not t:
        return False
    import re
    t2 = re.sub(
        r"^(لطفا|خواهشا|میشه|میتونی|می‌تونی)\s*",
        "",
        t,
        flags=re.I,
    ).strip()
    patterns = (
        r"^ویس\s*بفرست\s*$",
        r"^صدا\s*بفرست\s*$",
        r"^بفرست\s*ویس\s*$",
        r"^بفرست\s*صدا\s*$",
        r"^با\s*ویس\s*$",
        r"^با\s*صدا\s*$",
        r"^بخون\s*$",
        r"^بخوان\s*$",
        r"^voice\s*$",
        r"^tts\s*$",
        r"^فایل\s*صوتی\s*بفرست\s*$",
    )
    return any(re.search(p, t2, re.I) for p in patterns)



def strip_voice_prefix(text: str) -> str:
    import re
    t = (text or "").strip()
    t = re.sub(
        r"^(با\s*ویس|با\s*صدا|ویس|صدا)\s*[:：]?\s*",
        "",
        t,
        flags=re.I,
    )
    t = re.sub(r"\b(با\s*ویس\s*بگو|با\s*صدا\s*بگو)\b", "", t, flags=re.I)
    return t.strip() or text.strip()


def should_auto_voice_reply(
    user_text: str,
    answer: str,
    *,
    input_was_voice: bool = False,
    explicit_voice: bool = False,
    voice_chat_mode: bool = False,
) -> bool:
    """
    ویس فقط وقتی:
      ۱) کاربر صریحاً خواسته (با ویس / بخون / ...)
      ۲) حالت مکالمه ویسی روشن است («ویس حرف بزنیم»)
    ورودی ویس به‌تنهایی کافی نیست — الکی ویس نمی‌فرستد.
    """
    ans = (answer or "").strip()
    if not ans:
        return False

    # فقط درخواست صریح یا حالت مکالمه ویسی
    if explicit_voice or voice_chat_mode:
        return True

    return False




# ── موسیقی / افکت صوتی (Gemini Lyria در صورت پشتیبانی کلید) ────────────────

async def generate_music(prompt: str) -> bytes:
    """
    ساخت کلیپ صوتی.
    اولویت: مدل‌های Lyria / پاسخ AUDIO در Gemini.
    اگر API موسیقی ندهد، خطای واضح برمی‌گرداند.
    """
    prompt = (prompt or "").strip()
    if not prompt:
        raise RuntimeError("توضیح موسیقی خالی است.")
    keys = _next_keys("gemini")
    if not keys:
        raise RuntimeError("برای ساخت موسیقی به کلید Gemini نیاز است.")

    models = [
        os.getenv("GEMINI_MUSIC_MODEL", "").strip(),
        "lyria-3-clip-preview",
        "lyria-3-pro-preview",
    ]
    models = [m for m in models if m]
    # حذف تکراری با حفظ ترتیب
    seen = set()
    models = [m for m in models if not (m in seen or seen.add(m))]

    errors = []
    for model in models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        payloads = [{
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"responseModalities": ["AUDIO"]},
        }]
        for key in keys:
            for payload in payloads:
                try:
                    status, data = await _post_json(url, params={"key": key}, json=payload)
                    if status >= 400:
                        errors.append(f"{model} HTTP {status}")
                        if _is_quota_error(status, data):
                            _mark_key_cooldown("gemini", key, daily=True)
                        continue
                    parts = (data.get("candidates") or [{}])[0].get("content", {}).get("parts") or []
                    for part in parts:
                        inline = part.get("inlineData") or part.get("inline_data")
                        if inline and inline.get("data"):
                            raw = base64.b64decode(inline["data"])
                            if raw:
                                _advance_rr("gemini")
                                return raw
                    errors.append(f"{model}: no audio part")
                except Exception as e:
                    errors.append(str(e)[:120])
    raise RuntimeError(
        "ساخت موسیقی روی این کلید/مدل در دسترس نبود. "
        "مدل Lyria باید روی پروژه Google AI Studio فعال باشد.\n"
        + " | ".join(errors[:5])
    )



async def analyze_video(
    video_bytes: bytes,
    prompt: str = "",
    *,
    mime: str = "video/mp4",
) -> str:
    """تحلیل ویدیو کوتاه با Gemini."""
    keys = _next_keys("gemini")
    if not keys:
        raise RuntimeError("برای تحلیل ویدیو به Gemini نیاز است.")
    if len(video_bytes) > 15_000_000:
        raise RuntimeError("ویدیو خیلی بزرگ است (حد حدود ۱۵ مگ).")

    model = os.getenv("GEMINI_VIDEO_MODEL", "gemini-3.5-flash-lite")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    text = (prompt or "").strip() or (
        "این ویدیو کوتاه را خلاصه و تحلیل کن: موضوع، افراد/اشیاء مهم، "
        "متن یا گفتار شنیده‌شده، و نکات کلیدی."
    )
    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {
                        "inline_data": {
                            "mime_type": mime or "video/mp4",
                            "data": base64.b64encode(video_bytes).decode("ascii"),
                        }
                    },
                    {"text": text},
                ],
            }
        ],
        "generationConfig": {"maxOutputTokens": MAX_OUTPUT},
    }
    errors = []
    for key in keys:
        try:
            status, data = await _post_json(url, params={"key": key}, json=payload)
            if status >= 400:
                if _is_quota_error(status, data):
                    _mark_key_cooldown("gemini", key, daily=True)
                errors.append(f"HTTP {status}")
                continue
            parts = data["candidates"][0]["content"]["parts"]
            out = "".join(x.get("text", "") for x in parts).strip()
            if out:
                _advance_rr("gemini")
                return out
        except Exception as e:
            errors.append(str(e)[:150])
    raise RuntimeError("تحلیل ویدیو ناموفق: " + " | ".join(errors[:4]))


async def translate_voice(
    audio_bytes: bytes,
    *,
    target_lang: str = "en",
    filename: str = "voice.ogg",
    mime: str = "audio/ogg",
) -> tuple[str, str, bytes]:
    """ویس → متن → ترجمه → ویس مقصد. خروجی: (متن اصلی, ترجمه, audio)."""
    src_text = await speech_to_text(audio_bytes, filename=filename, mime=mime)
    target_lang = (target_lang or "en").lower()
    lang_name = {
        "en": "English",
        "fa": "Persian",
        "ar": "Arabic",
        "tr": "Turkish",
        "de": "German",
        "fr": "French",
    }.get(target_lang, target_lang)

    prompt = (
        "Translate the following text to "
        + lang_name
        + ". Return only the translation.\n\n"
        + src_text
    )
    translated = None
    options = available_model_options()
    for provider, _label, model in options:
        try:
            translated = await _call_provider(provider, 0, prompt, model)
            if translated:
                break
        except Exception:
            continue
    if not translated:
        raise RuntimeError("ترجمه ناموفق بود.")

    voice = TTS_VOICE
    if target_lang.startswith("en"):
        voice = "en-US-JennyNeural"
    elif target_lang.startswith("ar"):
        voice = "ar-SA-ZariyahNeural"
    elif target_lang.startswith("de"):
        voice = "de-DE-KatjaNeural"
    elif target_lang.startswith("fr"):
        voice = "fr-FR-DeniseNeural"
    elif target_lang.startswith("tr"):
        voice = "tr-TR-EmelNeural"
    elif target_lang.startswith("fa"):
        voice = TTS_VOICE

    audio_out = await text_to_speech(translated, voice=voice)
    return src_text, translated, audio_out



async def ask_ai(user_id: int, prompt: str) -> tuple[str, str]:
    prompt = (prompt or "").strip()
    if not prompt:
        raise RuntimeError("پیام خالی است")
    if len(prompt) > MAX_INPUT:
        prompt = prompt[:MAX_INPUT]

    options = available_model_options()
    if not options:
        raise RuntimeError(
            "هیچ سرویس AI تنظیم نشده است. حداقل یک API Key در Render قرار بده."
        )

    original_prompt = prompt
    try:
        _extract_and_store_memory(user_id, original_prompt)
    except Exception:
        pass
    # ساخت لیست (provider, model) برای امتحان — سریع‌ترین‌ها اول
    def _models_of(provider: str) -> List[Tuple[str, str]]:
        return [(provider, m) for m in models_for_provider(provider)]

    async with _LOCKS[user_id]:
        selected = get_selected_model(user_id)
        ordered: List[Tuple[str, str]] = []
        tried: set = set()
        errors: List[str] = []

        # ۱) اگر کاربر ارائه‌دهنده انتخاب کرده → همه مدل‌های همان ارائه‌دهنده
        if selected:
            provider, model = selected
            available_for_selected = _models_of(provider)
            if not available_for_selected:
                selected = None
            if model == "*" or model is None:
                ordered.extend(available_for_selected)
            else:
                # اگر مدل قدیمی حذف شده باشد، آن را کورکورانه صدا نزن؛
                # اول نزدیک‌ترین مدل فعال همان provider را امتحان کن.
                if (provider, model) in available_for_selected:
                    ordered.append((provider, model))
                ordered.extend(
                    item for item in available_for_selected if item not in ordered
                )

        # ۲) بقیه ارائه‌دهنده‌ها (fallback) به ترتیب پیش‌فرض
        for provider, _label, model in options:
            item = (provider, model)
            if item not in ordered:
                ordered.append(item)

        for provider, model in ordered:
            key = (provider, model)
            if key in tried:
                continue
            tried.add(key)
            try:
                answer = await _call_provider(provider, user_id, prompt, model)
                _save_turn(user_id, original_prompt, answer)
                # اگر هنوز provider انتخاب نشده، همین را ذخیره کن (با *)
                if not selected:
                    set_selected_model(user_id, provider, "*")
                return answer, f"{provider} / {model}"
            except Exception as exc:
                msg = str(exc).replace("\n", " ")[:500]
                errors.append(f"{provider}/{model}: {msg}")
                logger.warning("AI provider/model failed: %s", msg)
                # تأخیر خیلی کم بین تلاش‌ها برای سرعت بیشتر
                await asyncio.sleep(0.05)

    raise RuntimeError(
        "فعلاً هیچ‌کدام از مدل‌های AI پاسخ ندادند.\n\n" + "\n".join(errors[:8])
    )


# ── استریم واقعی از API (SSE) ───────────────────────────────────────────────

async def _stream_openai_compatible(
    provider: str,
    user_id: int,
    prompt: str,
    *,
    url: str,
    model: str,
    extra_headers=None,
):
    """ییلد تکه‌های متن از chat/completions با stream=true."""
    import json as _json

    keys = _next_keys(provider)
    if not keys:
        raise RuntimeError(f"no keys for {provider}")

    last_err = None
    for key in keys:
        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }
        if extra_headers:
            headers.update(extra_headers)
        payload = {
            "model": model,
            "messages": _messages(user_id, prompt),
            "max_tokens": MAX_OUTPUT,
            "temperature": 0.6,
            "stream": True,
        }
        client = _get_http()
        try:
            async with client.stream("POST", url, headers=headers, json=payload) as resp:
                if resp.status_code >= 400:
                    body = (await resp.aread())[:500]
                    if _is_quota_error(resp.status_code, body):
                        _mark_key_cooldown(provider, key, daily=True)
                        last_err = f"HTTP {resp.status_code}"
                        continue
                    raise RuntimeError(f"stream HTTP {resp.status_code}: {body!r}")
                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    if line.startswith("data:"):
                        data = line[5:].strip()
                    else:
                        continue
                    if data == "[DONE]":
                        break
                    try:
                        obj = _json.loads(data)
                    except Exception:
                        continue
                    choices = obj.get("choices") or []
                    if not choices:
                        continue
                    delta = choices[0].get("delta") or {}
                    piece = delta.get("content") or ""
                    if piece:
                        yield piece
            _advance_rr(provider)
            return
        except Exception as e:
            last_err = str(e)
            continue
    raise RuntimeError(last_err or "stream failed")


async def _stream_gemini(user_id: int, prompt: str, model: str):
    """استریم Gemini با streamGenerateContent?alt=sse."""
    import json as _json

    keys = _next_keys("gemini")
    if not keys:
        raise RuntimeError("no gemini keys")

    contents = []
    mem = _memory_block(user_id)
    system = SYSTEM_PROMPT + ("\n\n" + mem if mem else "")
    for role, content in _HISTORY[user_id]:
        contents.append(
            {
                "role": "model" if role == "assistant" else "user",
                "parts": [{"text": content}],
            }
        )
    contents.append({"role": "user", "parts": [{"text": prompt}]})
    payload = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": contents,
        "generationConfig": {"maxOutputTokens": MAX_OUTPUT},
    }
    last_err = None
    for key in keys:
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}"
            f":streamGenerateContent"
        )
        client = _get_http()
        try:
            async with client.stream(
                "POST", url, params={"key": key, "alt": "sse"}, json=payload
            ) as resp:
                if resp.status_code >= 400:
                    body = (await resp.aread())[:400]
                    if _is_quota_error(resp.status_code, body):
                        _mark_key_cooldown("gemini", key, daily=True)
                        last_err = f"HTTP {resp.status_code}"
                        continue
                    raise RuntimeError(f"gemini stream HTTP {resp.status_code}")
                async for line in resp.aiter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if not data or data == "[DONE]":
                        continue
                    try:
                        obj = _json.loads(data)
                        parts = obj["candidates"][0]["content"]["parts"]
                        for p in parts:
                            t = p.get("text") or ""
                            if t:
                                yield t
                    except Exception:
                        continue
            _advance_rr("gemini")
            return
        except Exception as e:
            last_err = str(e)
            continue
    raise RuntimeError(last_err or "gemini stream failed")


async def ask_ai_stream(user_id: int, prompt: str):
    """
    Async generator: ییلد (chunk:str | None, provider_label:str | None)
    در پایان یک بار (None, "provider / model") می‌فرستد.
    اگر استریم ممکن نبود، کل جواب را یک‌جا ییلد می‌کند.
    """
    prompt = (prompt or "").strip()
    if not prompt:
        raise RuntimeError("پیام خالی است")
    if len(prompt) > MAX_INPUT:
        prompt = prompt[:MAX_INPUT]

    original = prompt
    try:
        _extract_and_store_memory(user_id, original)
    except Exception:
        pass
    options = available_model_options()
    if not options:
        raise RuntimeError("هیچ سرویس AI تنظیم نشده")

    # Streaming endpoints in this project intentionally do not execute function calls.
    # For tool-intent prompts, use the authoritative non-stream path so live data is correct.
    try:
        from bot.services.ai_tools import prompt_has_keyword_tool
        if prompt_has_keyword_tool(original):
            answer, label = await ask_ai(user_id, original)
            yield answer, None
            yield None, label
            return
    except Exception:
        pass

    async with _LOCKS[user_id]:
        selected = get_selected_model(user_id)
        ordered: List[Tuple[str, str]] = []
        if selected:
            provider, model = selected
            if not models_for_provider(provider):
                selected = None
            elif model == "*" or model is None:
                ordered.extend((provider, m) for m in models_for_provider(provider))
            else:
                ordered.append((provider, model))
                for m in models_for_provider(provider):
                    if (provider, m) not in ordered:
                        ordered.append((provider, m))
        for provider, _label, model in options:
            if (provider, model) not in ordered:
                ordered.append((provider, model))

        errors = []
        for provider, model in ordered:
            full = []
            try:
                if provider in ("groq", "cerebras", "openrouter"):
                    if provider == "groq":
                        url = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1").rstrip("/") + "/chat/completions"
                        extra_h = None
                    elif provider == "cerebras":
                        url = "https://api.cerebras.ai/v1/chat/completions"
                        extra_h = None
                    else:
                        url = "https://openrouter.ai/api/v1/chat/completions"
                        extra_h = {"HTTP-Referer": "https://t.me", "X-Title": "RoozeZiba"}
                    async for piece in _stream_openai_compatible(
                        provider, user_id, prompt, url=url, model=model, extra_headers=extra_h
                    ):
                        full.append(piece)
                        yield piece, None
                elif provider == "gemini":
                    async for piece in _stream_gemini(user_id, prompt, model):
                        full.append(piece)
                        yield piece, None
                else:
                    # fallback غیر استریم
                    answer = await _call_provider(provider, user_id, prompt, model)
                    full.append(answer)
                    yield answer, None

                answer = "".join(full).strip()
                if not answer:
                    raise RuntimeError("empty stream")
                _save_turn(user_id, original, answer)
                if not selected:
                    set_selected_model(user_id, provider, "*")
                yield None, f"{provider} / {model}"
                return
            except Exception as e:
                errors.append(f"{provider}/{model}: {str(e)[:200]}")
                logger.warning("stream failed: %s", e)
                await asyncio.sleep(0.05)
                continue

    raise RuntimeError("استریم ناموفق:\n" + "\n".join(errors[:6]))


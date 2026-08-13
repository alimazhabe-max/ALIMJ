"""AI router, per-user model selection, and multi-key rotation for Rooze Ziba."""
from __future__ import annotations

import asyncio
import os
import time
from collections import defaultdict, deque
from typing import Deque, Dict, List, Optional, Tuple

import httpx

from bot.logger import logger

# ── System Prompt ───────────────────────────────────────────────────────────
SYSTEM_PROMPT = os.getenv(
    "AI_SYSTEM_PROMPT",
    "تو دستیار هوشمند ربات «روز زیبا» هستی. "
    "با لحنی گرم، طبیعی، محترمانه و کمی شوخ‌طبع (فقط وقتی فضا مناسب است) فارسی روان صحبت کن. "
    "اگر کاربر به زبان دیگری پیام داد، دقیقاً به همان زبان پاسخ بده. "
    "پاسخ‌هایت باید کامل، مفصل و جامع باشد. هرگز جواب را خلاصه نکن مگر اینکه کاربر صریحاً بگوید «خلاصه بگو» یا «کوتاه». "
    "جزئیات مهم، مثال‌ها، مراحل و نکات کاربردی را بنویس تا کاربر واقعاً متوجه شود و نیاز به پرسش دوباره نداشته باشد. "
    "از حاشیه‌روی بی‌ربط و جملات کلیشه‌ای پرهیز کن، اما کوتاه‌کردن عمدی محتوا ممنوع است. "
    "هرگز اطلاعات زنده، لحظه‌ای یا به‌روز (مثل قیمت ارز/طلا، خبر، وضعیت آب‌وهوا، نتیجه مسابقه و ...) را بدون ابزار ادعا نکن. "
    "اگر مطمئن نیستی یا نیاز به دادهٔ تازه داری، صادقانه بگو. "
    "هدف تو این است که کاربر حس کند با یک دستیار باهوش، قابل‌اعتماد و مفید حرف می‌زند که جواب کامل می‌دهد.",
)

MAX_INPUT = int(os.getenv("AI_MAX_INPUT", "6000"))
# سقف خروجی بالاتر تا جواب‌ها کامل و مفصل باشند
MAX_OUTPUT = int(os.getenv("AI_MAX_OUTPUT", "2800"))
HISTORY_ITEMS = max(2, int(os.getenv("AI_HISTORY_ITEMS", "20")))
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

def clear_history(user_id: int) -> None:
    _HISTORY.pop(user_id, None)


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
        # flash-lite اول = سریع‌تر
        for model in _env_models(
            "GEMINI_MODELS",
            ["gemini-3.1-flash-lite", "gemini-3.5-flash"],
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


def _messages(user_id: int, prompt: str) -> List[dict]:
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for role, content in _HISTORY[user_id]:
        messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": prompt})
    return messages


def _save_turn(user_id: int, prompt: str, answer: str) -> None:
    history = _HISTORY[user_id]
    history.append(("user", prompt))
    history.append(("assistant", answer))


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

async def _gemini(user_id: int, prompt: str, model: str) -> str:
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
    contents.append({"role": "user", "parts": [{"text": prompt}]})
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
                parts = data["candidates"][0]["content"]["parts"]
                text = "".join(p.get("text", "") for p in parts).strip()
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
            # خطای غیرسهمیه: همان کلید را رد کن ولی cooldown نزن
            errors.append(str(exc)[:200])
            continue

    raise RuntimeError("همه کلیدهای Gemini تمام/خطا: " + " | ".join(errors[:5]))


async def _openai_compatible(
    name: str,
    provider: str,
    user_id: int,
    prompt: str,
    *,
    url: str,
    model: str,
    extra_headers=None,
) -> str:
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

        payload = {
            "model": model,
            "messages": _messages(user_id, prompt),
            "max_tokens": MAX_OUTPUT,
            "temperature": 0.6,
        }

        try:
            status, data = await _post_json(url, headers=headers, json=payload)
            if status >= 400:
                if _is_quota_error(status, data):
                    daily = "daily" in str(data).lower() or "quota" in str(data).lower() or status == 403
                    _mark_key_cooldown(provider, key, daily=daily or status == 429)
                    errors.append(f"{_key_id(provider, key)} HTTP {status}")
                    continue
                raise RuntimeError(f"{name} HTTP {status}: {str(data)[:900]}")

            text = _extract_openai(data)
            _advance_rr(provider)
            return text
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
            if model == "*" or model is None:
                ordered.extend(_models_of(provider))
            else:
                # مدل خاص انتخاب شده بود — اول همون، بعد بقیه مدل‌های همون provider
                ordered.append((provider, model))
                for item in _models_of(provider):
                    if item not in ordered:
                        ordered.append(item)

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
                _save_turn(user_id, prompt, answer)
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

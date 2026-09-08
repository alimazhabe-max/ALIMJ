"""Shared AI runtime state, configuration, routing and key-pool helpers (V26)."""
from __future__ import annotations

import asyncio
import os
import time
from collections import defaultdict, deque
from typing import Deque, Dict, List, Optional, Tuple

import httpx

from bot.logger import logger

GEMINI_SAFETY_SETTINGS = [
    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_CIVIC_INTEGRITY", "threshold": "BLOCK_NONE"},
]

# خاموش کردن فیلترهای ایمنی Gemini برای اجازه به محتوای بزرگسال/صریح
GEMINI_SAFETY_SETTINGS = [
    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_CIVIC_INTEGRITY", "threshold": "BLOCK_NONE"},
]

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
AI_RETRY_COUNT = max(0, int(os.getenv("AI_RETRY_COUNT", "2")))
AI_RETRY_BASE_SEC = float(os.getenv("AI_RETRY_BASE_SEC", "0.25"))
AI_SIMPLE_MAX_CHARS = int(os.getenv("AI_SIMPLE_MAX_CHARS", "220"))
AI_COMPLEX_MIN_CHARS = int(os.getenv("AI_COMPLEX_MIN_CHARS", "1200"))
AI_PROVIDER_FAILURE_THRESHOLD = max(2, int(os.getenv("AI_PROVIDER_FAILURE_THRESHOLD", "3")))
AI_PROVIDER_COOLDOWN_SEC = max(10.0, float(os.getenv("AI_PROVIDER_COOLDOWN_SEC", "45")))
AI_PROVIDER_MAX_COOLDOWN_SEC = max(AI_PROVIDER_COOLDOWN_SEC, float(os.getenv("AI_PROVIDER_MAX_COOLDOWN_SEC", "300")))
# V5 adaptive quality/cost routing. Values are heuristics and can be overridden
# per model/provider without hard-coding vendor pricing into the bot.
AI_ROUTING_COST_WEIGHT = float(os.getenv("AI_ROUTING_COST_WEIGHT", "0.35"))
AI_ROUTING_QUALITY_WEIGHT = float(os.getenv("AI_ROUTING_QUALITY_WEIGHT", "0.65"))
AI_ROUTING_LATENCY_WEIGHT = float(os.getenv("AI_ROUTING_LATENCY_WEIGHT", "0.20"))
AI_ROUTING_MODE = os.getenv("AI_ROUTING_MODE", "balanced").strip().lower()

# Optional JSON-like profiles: provider/model=cost,quality, e.g.
# AI_MODEL_PROFILES='groq/llama-3.1-8b-instant=0.15,0.65;gemini/gemini-3.6-flash=0.35,0.90'
def _load_model_profiles() -> Dict[Tuple[str, str], Tuple[float, float]]:
    profiles: Dict[Tuple[str, str], Tuple[float, float]] = {}
    raw = os.getenv("AI_MODEL_PROFILES", "")
    for item in raw.split(";"):
        item = item.strip()
        if not item or "=" not in item:
            continue
        key, values = item.split("=", 1)
        parts = [x.strip() for x in values.split(",")]
        if "/" not in key or len(parts) < 2:
            continue
        provider, model = [x.strip().lower() for x in key.split("/", 1)]
        try:
            profiles[(provider, model)] = (max(0.0, min(1.0, float(parts[0]))), max(0.0, min(1.0, float(parts[1]))))
        except ValueError:
            continue
    return profiles

_AI_MODEL_PROFILES = _load_model_profiles()

def _model_profile(provider: str, model: str) -> Tuple[float, float]:
    key = (provider.lower(), model.lower())
    if key in _AI_MODEL_PROFILES:
        return _AI_MODEL_PROFILES[key]
    # Conservative name-based defaults; explicit profiles always win.
    name = model.lower()
    quality = 0.70
    cost = 0.45
    if any(x in name for x in ("8b", "3b", "lite", "instant", "flash-lite")):
        quality, cost = 0.62, 0.18
    elif any(x in name for x in ("70b", "120b", "pro", "opus", "sonnet")):
        quality, cost = 0.92, 0.72
    elif "flash" in name:
        quality, cost = 0.82, 0.38
    return cost, quality

def _route_score(provider: str, model: str, *, complex_request: bool) -> float:
    cost, quality = _model_profile(provider, model)
    health = _provider_rank(provider)
    latency = min(health, 8.0) / 8.0
    if AI_ROUTING_MODE == "quality":
        cost_w, quality_w, latency_w = 0.10, 1.00, 0.10
    elif AI_ROUTING_MODE == "economy":
        cost_w, quality_w, latency_w = 1.00, 0.35, 0.15
    elif AI_ROUTING_MODE == "speed":
        cost_w, quality_w, latency_w = 0.25, 0.45, 1.00
    else:
        cost_w, quality_w, latency_w = AI_ROUTING_COST_WEIGHT, AI_ROUTING_QUALITY_WEIGHT, AI_ROUTING_LATENCY_WEIGHT
    # Complex prompts need quality more strongly; simple prompts benefit from economy.
    if complex_request:
        quality_w *= 1.35
    else:
        cost_w *= 1.20
    return (cost * cost_w) + ((1.0 - quality) * quality_w) + (latency * latency_w)

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

# Adaptive provider health: faster/healthier providers move up automatically.
_PROVIDER_HEALTH: Dict[str, Dict[str, float]] = defaultdict(
    lambda: {
        "ok": 0.0, "fail": 0.0, "latency": 0.0,
        "last_fail": 0.0, "last_ok": 0.0,
        "consecutive_fail": 0.0, "cooldown_until": 0.0,
    }
)

def _provider_rank(provider: str) -> float:
    """Adaptive score with time decay so old failures don't poison routing forever."""
    h = _PROVIDER_HEALTH[provider]
    now = time.time()
    age = max(0.0, now - max(h["last_fail"], h["last_ok"]))
    decay = 0.5 ** (age / 600.0)  # 10-minute half-life
    ok = h["ok"] * decay
    fail = h["fail"] * decay
    latency = (h["latency"] / h["ok"]) if h["ok"] else 3.0
    recent_penalty = 2.0 if h["last_fail"] and now - h["last_fail"] < 20 else 0.0
    return (fail * 2.5) + recent_penalty + min(latency, 8.0) * 0.15 - min(ok, 20.0) * 0.02

def _provider_available(provider: str, *, explicit: bool = False) -> bool:
    """Return whether a provider is currently eligible for automatic routing."""
    if explicit:
        return True
    return time.time() >= _PROVIDER_HEALTH[provider]["cooldown_until"]

def _record_provider(provider: str, *, ok: bool, latency: float) -> None:
    h = _PROVIDER_HEALTH[provider]
    now = time.time()
    if ok:
        h["ok"] += 1
        h["latency"] += max(0.0, latency)
        h["last_ok"] = now
        h["consecutive_fail"] = 0.0
        h["cooldown_until"] = 0.0
    else:
        h["fail"] += 1
        h["last_fail"] = now
        h["consecutive_fail"] += 1
        if h["consecutive_fail"] >= AI_PROVIDER_FAILURE_THRESHOLD:
            exponent = min(h["consecutive_fail"] - AI_PROVIDER_FAILURE_THRESHOLD, 4.0)
            cooldown = min(AI_PROVIDER_MAX_COOLDOWN_SEC, AI_PROVIDER_COOLDOWN_SEC * (2.0 ** exponent))
            h["cooldown_until"] = max(h["cooldown_until"], now + cooldown)
            logger.warning("AI provider %s circuit-open for %.1fs after %.0f consecutive failures", provider, cooldown, h["consecutive_fail"])



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
    try:
        from bot.utils.http_client import close_async_client
        await close_async_client()
    except Exception:
        pass

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


def _valid_selected_model(pref: Tuple[str, str] | None) -> Tuple[str, str] | None:
    """Return a saved selection only if its provider/model still exists."""
    if not pref:
        return None
    provider, model = pref
    provider = (provider or "").strip().lower()
    model = (model or "*").strip()
    if provider not in {p for p, _label, _model in available_model_options()}:
        return None
    models = models_for_provider(provider)
    if not models:
        return None
    if model == "*" or model in models:
        return provider, model
    return provider, "*"

def get_selected_model(user_id: int) -> Tuple[str, str] | None:
    if user_id in _USER_SELECTION:
        return _USER_SELECTION[user_id]
    try:
        from bot.database import get_ai_preference
        pref = get_ai_preference(user_id)
        if pref:
            valid = _valid_selected_model(pref)
            if valid:
                _USER_SELECTION[user_id] = valid
                if valid != pref:
                    try:
                        set_ai_preference(user_id, valid[0], valid[1])
                    except Exception:
                        pass
                return valid
            clear_selected_model(user_id)
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
            ["gemini-3.5-flash-lite", "gemini-3.6-flash", "gemini-3.1-flash-lite"],
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



__all__ = [name for name in globals() if not name.startswith("__")]

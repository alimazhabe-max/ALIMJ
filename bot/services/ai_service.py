"""AI router and per-user model selection for Rooze Ziba."""
from __future__ import annotations

import asyncio
import os
from collections import defaultdict, deque
from typing import Deque, Dict, List, Tuple

import httpx

from bot.logger import logger

SYSTEM_PROMPT = os.getenv(
    "AI_SYSTEM_PROMPT",
    "تو دستیار هوشمند ربات «روز زیبا» هستی. "
    "با لحنی گرم، طبیعی، محترمانه و کمی شوخ‌طبع (در صورت مناسب بودن فضا) فارسی روان صحبت کن. "
    "اگر کاربر به زبان دیگری پیام داد، دقیقاً به همان زبان پاسخ بده. "
    "پاسخ‌هایت باید واضح، کاربردی، کامل و مستقیم باشد؛ از حاشیه‌روی و جملات کلیشه‌ای پرهیز کن. "
    "هرگز اطلاعات زنده، لحظه‌ای یا به‌روز (مثل قیمت، خبر، وضعیت آب‌وهوا، نتیجه مسابقه و ...) را بدون استفاده از ابزار ادعا نکن. "
    "اگر مطمئن نیستی یا نیاز به دادهٔ تازه داری، صادقانه بگو و در صورت امکان از ابزار استفاده کن. "
    "هدف تو این است که کاربر حس کند با یک دستیار باهوش، قابل‌اعتماد و مفید حرف می‌زند.",
)

MAX_INPUT = int(os.getenv("AI_MAX_INPUT", "5000"))
MAX_OUTPUT = int(os.getenv("AI_MAX_OUTPUT", "1200"))
HISTORY_ITEMS = max(2, int(os.getenv("AI_HISTORY_ITEMS", "8")))
TIMEOUT = float(os.getenv("AI_TIMEOUT", "35"))

# user_id -> short conversation history
_HISTORY: Dict[int, Deque[Tuple[str, str]]] = defaultdict(
    lambda: deque(maxlen=HISTORY_ITEMS)
)
_LOCKS: Dict[int, asyncio.Lock] = defaultdict(asyncio.Lock)

# user_id -> (provider, model)
_USER_SELECTION: Dict[int, Tuple[str, str]] = {}


def clear_history(user_id: int) -> None:
    _HISTORY.pop(user_id, None)


def get_selected_model(user_id: int) -> Tuple[str, str] | None:
    return _USER_SELECTION.get(user_id)


def set_selected_model(user_id: int, provider: str, model: str) -> None:
    _USER_SELECTION[user_id] = (provider, model)


def _env_models(env_name: str, default: List[str]) -> List[str]:
    raw = os.getenv(env_name, "")
    values = [x.strip() for x in raw.split(",") if x.strip()]
    return values or default


def available_model_options() -> List[Tuple[str, str, str]]:
    """
    Returns (provider_key, display_name, model_id).
    A provider is shown only when its credentials are configured.
    """
    options: List[Tuple[str, str, str]] = []

    if os.getenv("GEMINI_API_KEY"):
        for model in _env_models(
            "GEMINI_MODELS",
            ["gemini-3.1-flash-lite", "gemini-3.5-flash"],
        ):
            label = "Gemini • " + model.replace("gemini-", "Gemini ")
            options.append(("gemini", label, model))

    if os.getenv("GROQ_API_KEY"):
        for model in _env_models(
            "GROQ_MODELS",
            [
                "llama-3.1-8b-instant",
                "llama-3.3-70b-versatile",
                "openai/gpt-oss-20b",
                "openai/gpt-oss-120b",
            ],
        ):
            options.append(("groq", "Groq • " + model, model))

    if os.getenv("CEREBRAS_API_KEY"):
        for model in _env_models("CEREBRAS_MODELS", [os.getenv("CEREBRAS_MODEL", "gpt-oss-120b")]):
            options.append(("cerebras", "Cerebras • " + model, model))

    if os.getenv("CLOUDFLARE_ACCOUNT_ID") and os.getenv("CLOUDFLARE_AUTH_TOKEN"):
        for model in _env_models(
            "CLOUDFLARE_MODELS",
            [os.getenv("CLOUDFLARE_MODEL", "@cf/meta/llama-3.2-3b-instruct")],
        ):
            options.append(("cloudflare", "Cloudflare • " + model, model))

    if os.getenv("OPENROUTER_API_KEY"):
        for model in _env_models("OPENROUTER_MODELS", [os.getenv("OPENROUTER_MODEL", "openrouter/free")]):
            options.append(("openrouter", "OpenRouter • " + model, model))

    return options


def enabled_providers() -> List[str]:
    seen = []
    for provider, _label, _model in available_model_options():
        pretty = {
            "gemini": "Gemini",
            "groq": "Groq",
            "cerebras": "Cerebras",
            "cloudflare": "Cloudflare",
            "openrouter": "OpenRouter",
        }.get(provider, provider)
        if pretty not in seen:
            seen.append(pretty)
    return seen


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
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
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


async def _gemini(user_id: int, prompt: str, model: str) -> str:
    key = os.environ["GEMINI_API_KEY"]
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

    status, data = await _post_json(url, params={"key": key}, json=payload)
    if status >= 400:
        raise RuntimeError(f"Gemini HTTP {status}: {str(data)[:900]}")

    try:
        parts = data["candidates"][0]["content"]["parts"]
        text = "".join(p.get("text", "") for p in parts).strip()
    except Exception:
        raise RuntimeError(f"Gemini unexpected response: {str(data)[:900]}")

    if not text:
        raise RuntimeError("Gemini returned an empty answer")
    return text


async def _openai_compatible(
    name: str,
    user_id: int,
    prompt: str,
    *,
    key_env: str,
    url: str,
    model: str,
    extra_headers=None,
) -> str:
    key = os.environ[key_env]
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

    status, data = await _post_json(url, headers=headers, json=payload)
    if status >= 400:
        raise RuntimeError(f"{name} HTTP {status}: {str(data)[:900]}")

    return _extract_openai(data)


async def _groq(user_id: int, prompt: str, model: str) -> str:
    return await _openai_compatible(
        "Groq",
        user_id,
        prompt,
        key_env="GROQ_API_KEY",
        url=os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1").rstrip("/") + "/chat/completions",
        model=model,
    )


async def _cerebras(user_id: int, prompt: str, model: str) -> str:
    return await _openai_compatible(
        "Cerebras",
        user_id,
        prompt,
        key_env="CEREBRAS_API_KEY",
        url="https://api.cerebras.ai/v1/chat/completions",
        model=model,
    )


async def _openrouter(user_id: int, prompt: str, model: str) -> str:
    return await _openai_compatible(
        "OpenRouter",
        user_id,
        prompt,
        key_env="OPENROUTER_API_KEY",
        url="https://openrouter.ai/api/v1/chat/completions",
        model=model,
        extra_headers={"X-Title": "Rooze Ziba"},
    )


async def _cloudflare(user_id: int, prompt: str, model: str) -> str:
    account = os.environ["CLOUDFLARE_ACCOUNT_ID"]
    token = os.environ["CLOUDFLARE_AUTH_TOKEN"]
    url = f"https://api.cloudflare.com/client/v4/accounts/{account}/ai/run/{model}"

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    payload = {
        "messages": _messages(user_id, prompt),
        "max_tokens": MAX_OUTPUT,
    }

    status, data = await _post_json(url, headers=headers, json=payload)
    if status >= 400 or not data.get("success", True):
        raise RuntimeError(f"Cloudflare HTTP {status}: {str(data)[:900]}")

    result = data.get("result") or {}
    text = result.get("response") or result.get("text")
    if not text:
        raise RuntimeError(f"Cloudflare empty response: {str(data)[:900]}")
    return str(text).strip()


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


def _options_by_key() -> Dict[str, Tuple[str, str]]:
    return {
        f"{provider}:{model}": (provider, model)
        for provider, _label, model in available_model_options()
    }


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

    async with _LOCKS[user_id]:
        selected = _USER_SELECTION.get(user_id)

        # User-selected model gets first chance.
        if selected:
            provider, model = selected
            if f"{provider}:{model}" in _options_by_key():
                try:
                    answer = await _call_provider(provider, user_id, prompt, model)
                    _save_turn(user_id, prompt, answer)
                    return answer, f"{provider} / {model}"
                except Exception as exc:
                    logger.warning("Selected AI model failed: %s", exc)

        # Automatic failover: every configured model, excluding selected one first.
        tried = set()
        ordered = []
        if selected:
            ordered.append(selected)

        for provider, _label, model in options:
            item = (provider, model)
            if item not in ordered:
                ordered.append(item)

        errors = []
        for provider, model in ordered:
            key = (provider, model)
            if key in tried:
                continue
            tried.add(key)
            try:
                answer = await _call_provider(provider, user_id, prompt, model)
                _save_turn(user_id, prompt, answer)
                # Remember the model that actually worked for future messages.
                _USER_SELECTION[user_id] = (provider, model)
                return answer, f"{provider} / {model}"
            except Exception as exc:
                msg = str(exc).replace("\n", " ")[:500]
                errors.append(f"{provider}/{model}: {msg}")
                logger.warning("AI provider/model failed: %s", msg)
                await asyncio.sleep(0.1)

    raise RuntimeError(
        "فعلاً هیچ‌کدام از مدل‌های AI پاسخ ندادند.\n\n" + "\n".join(errors[:8])
    )

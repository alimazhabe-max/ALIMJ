"""روتر چند-سرویسه هوش مصنوعی برای ربات «روز زیبا».

مسیر فایل: bot/services/ai_service.py

- سرویس‌ها فقط وقتی فعال‌اند که کلید محیطی‌شان ست شده باشد
- مدل انتخابیِ کاربر (bot/services/ai_models.py) اولویت اول است
- در صورت خطا/محدودیت، خودکار روی بقیه سرویس‌ها fallback می‌شود
- هیچ کلیدی داخل کد hard-code نشده است
"""
from __future__ import annotations

import asyncio
import os
from collections import defaultdict, deque
from typing import Callable, Deque, Dict, List, Optional, Tuple

import httpx

from bot.logger import logger
from bot.services.ai_models import (
    MODELS,
    PROVIDER_LABEL,
    available_providers,
    get_user_model,
    provider_available,
)

SYSTEM_PROMPT = os.getenv(
    "AI_SYSTEM_PROMPT",
    "تو دستیار هوشمند ربات «روز زیبا» هستی. فارسی را روان، محترمانه و طبیعی پاسخ بده. "
    "اگر کاربر زبان دیگری استفاده کرد، به همان زبان پاسخ بده. پاسخ‌ها واضح، کوتاه و کاربردی باشند. "
    "از ادعای دانستن اطلاعات زنده بدون ابزار خودداری کن.",
)

MAX_INPUT = int(os.getenv("AI_MAX_INPUT", "5000"))
MAX_OUTPUT = int(os.getenv("AI_MAX_OUTPUT", "1200"))
HISTORY_ITEMS = int(os.getenv("AI_HISTORY_ITEMS", "12"))
TIMEOUT = float(os.getenv("AI_TIMEOUT", "60"))

# حافظه کوتاه‌مدت در حافظه فرآیند (محدود)
_HISTORY: Dict[int, Deque[Tuple[str, str]]] = defaultdict(lambda: deque(maxlen=HISTORY_ITEMS))
_LOCKS: Dict[int, asyncio.Lock] = defaultdict(asyncio.Lock)


def clear_history(user_id: int) -> None:
    _HISTORY.pop(user_id, None)


def enabled_providers() -> List[str]:
    """نام نمایشی سرویس‌های فعال."""
    return [PROVIDER_LABEL[p] for p in available_providers()]


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


async def _post_json(url: str, *, headers=None, json=None, params=None) -> Tuple[int, dict]:
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.post(url, headers=headers, json=json, params=params)
        try:
            data = response.json()
        except Exception:
            data = {"raw": response.text[:1500]}
        return response.status_code, data


def _extract_openai(data: dict) -> str:
    try:
        content = data["choices"][0]["message"]["content"]
    except Exception:
        raise RuntimeError(f"پاسخ نامعتبر: {str(data)[:900]}")
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(item.get("text", ""))
        content = "".join(parts)
    if not content:
        raise RuntimeError("سرویس پاسخ خالی برگرداند")
    return str(content).strip()


# ------------------------------------------------------------- providers

async def _gemini(user_id: int, prompt: str, model: Optional[str] = None) -> str:
    key = os.environ["GEMINI_API_KEY"]
    model = model or os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

    contents = []
    for role, content in _HISTORY[user_id]:
        contents.append({"role": "model" if role == "assistant" else "user", "parts": [{"text": content}]})
    contents.append({"role": "user", "parts": [{"text": prompt}]})

    payload = {
        "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": contents,
        "generationConfig": {"maxOutputTokens": MAX_OUTPUT, "temperature": 0.7},
    }
    status, data = await _post_json(url, params={"key": key}, json=payload)
    if status >= 400:
        raise RuntimeError(f"Gemini HTTP {status}: {str(data)[:600]}")
    try:
        parts = data["candidates"][0]["content"]["parts"]
        text = "".join(p.get("text", "") for p in parts).strip()
    except Exception:
        raise RuntimeError(f"Gemini پاسخ نامعتبر: {str(data)[:600]}")
    if not text:
        raise RuntimeError("Gemini پاسخ خالی برگرداند")
    return text


async def _openai_compatible(
    name: str,
    user_id: int,
    prompt: str,
    *,
    key_env: str,
    url: str,
    model: str,
    extra_headers: Optional[dict] = None,
) -> str:
    key = os.environ[key_env]
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
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
        raise RuntimeError(f"{name} HTTP {status}: {str(data)[:600]}")
    return _extract_openai(data)


async def _groq(user_id: int, prompt: str, model: Optional[str] = None) -> str:
    return await _openai_compatible(
        "Groq", user_id, prompt,
        key_env="GROQ_API_KEY",
        url=os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1") + "/chat/completions",
        model=model or os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
    )


async def _cerebras(user_id: int, prompt: str, model: Optional[str] = None) -> str:
    return await _openai_compatible(
        "Cerebras", user_id, prompt,
        key_env="CEREBRAS_API_KEY",
        url="https://api.cerebras.ai/v1/chat/completions",
        model=model or os.getenv("CEREBRAS_MODEL", "gpt-oss-120b"),
    )


async def _openrouter(user_id: int, prompt: str, model: Optional[str] = None) -> str:
    return await _openai_compatible(
        "OpenRouter", user_id, prompt,
        key_env="OPENROUTER_API_KEY",
        url="https://openrouter.ai/api/v1/chat/completions",
        model=model or os.getenv("OPENROUTER_MODEL", "deepseek/deepseek-chat-v3-0324:free"),
        extra_headers={"X-Title": "Rooze Ziba", "HTTP-Referer": "https://t.me/"},
    )


async def _cloudflare(user_id: int, prompt: str, model: Optional[str] = None) -> str:
    account = os.environ["CLOUDFLARE_ACCOUNT_ID"]
    token = os.environ["CLOUDFLARE_AUTH_TOKEN"]
    model = model or os.getenv("CLOUDFLARE_MODEL", "@cf/meta/llama-3.2-3b-instruct")
    url = f"https://api.cloudflare.com/client/v4/accounts/{account}/ai/run/{model}"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    payload = {"messages": _messages(user_id, prompt), "max_tokens": MAX_OUTPUT}
    status, data = await _post_json(url, headers=headers, json=payload)
    if status >= 400 or not data.get("success", True):
        raise RuntimeError(f"Cloudflare HTTP {status}: {str(data)[:600]}")
    result = data.get("result") or {}
    text = result.get("response") or result.get("text")
    if not text:
        raise RuntimeError(f"Cloudflare پاسخ خالی: {str(data)[:600]}")
    return str(text).strip()


_CALLERS: Dict[str, Callable] = {
    "gemini": _gemini,
    "groq": _groq,
    "cerebras": _cerebras,
    "openrouter": _openrouter,
    "cloudflare": _cloudflare,
}

# ترتیب پیش‌فرض fallback
_ORDER = ["gemini", "groq", "cerebras", "cloudflare", "openrouter"]


def _default_model_for(provider: str) -> Optional[str]:
    for m in MODELS:
        if m["provider"] == provider:
            return m["model"]
    return None


async def ask_ai(user_id: int, prompt: str) -> Tuple[str, str]:
    """پاسخ AI را برمی‌گرداند: (متن پاسخ، نام سرویس/مدل).

    ابتدا مدل انتخابی کاربر امتحان می‌شود، سپس بقیه سرویس‌های فعال.
    """
    prompt = (prompt or "").strip()
    if not prompt:
        raise RuntimeError("پیام خالی است")
    if len(prompt) > MAX_INPUT:
        prompt = prompt[:MAX_INPUT]

    attempts: List[Tuple[str, str, Optional[str]]] = []  # (label, provider, model)

    chosen = get_user_model(user_id)
    if chosen:
        attempts.append((f"{chosen['icon']} {chosen['name']}", chosen["provider"], chosen["model"]))

    for provider in _ORDER:
        if not provider_available(provider):
            continue
        if chosen and provider == chosen["provider"]:
            continue
        attempts.append((PROVIDER_LABEL[provider], provider, _default_model_for(provider)))

    if not attempts:
        raise RuntimeError(
            "هیچ سرویس هوش مصنوعی تنظیم نشده است.\n"
            "حداقل یکی از این کلیدها را در متغیرهای محیطی قرار بده:\n"
            "GEMINI_API_KEY / GROQ_API_KEY / CEREBRAS_API_KEY / OPENROUTER_API_KEY / CLOUDFLARE_*"
        )

    errors: List[str] = []
    async with _LOCKS[user_id]:
        for label, provider, model in attempts:
            fn = _CALLERS.get(provider)
            if not fn:
                continue
            try:
                answer = await fn(user_id, prompt, model)
                if answer:
                    _save_turn(user_id, prompt, answer)
                    return answer, label
            except Exception as exc:
                msg = str(exc).replace("\n", " ")[:400]
                errors.append(f"{label}: {msg}")
                logger.warning("AI provider failed: %s", msg)
                await asyncio.sleep(0.15)

    raise RuntimeError("\n".join(errors) if errors else "هیچ سرویس AI پاسخ نداد.")

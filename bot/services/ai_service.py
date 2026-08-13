"""Multi-provider AI router for Rooze Ziba.

Providers (enabled only when their environment variables exist):
1) Gemini
2) Groq
3) Cerebras
4) Cloudflare Workers AI
5) OpenRouter Free

The router fails over on transient errors, quota/rate-limit responses and provider errors.
No provider key is hard-coded here.
"""
from __future__ import annotations

import asyncio
import os
from collections import defaultdict, deque
from typing import Deque, Dict, List, Tuple

import httpx

from bot.logger import logger

SYSTEM_PROMPT = os.getenv(
    "AI_SYSTEM_PROMPT",
    """تو دستیار هوشمند ربات «روز زیبا» هستی. فارسی را روان، محترمانه و طبیعی پاسخ بده. """
    "اگر کاربر زبان دیگری استفاده کرد، به همان زبان پاسخ بده. پاسخ‌ها واضح و کاربردی باشند. """
    "از ادعای دانستن اطلاعات زنده بدون ابزار خودداری کن.""",
)

MAX_INPUT = int(os.getenv("AI_MAX_INPUT", "5000"))
MAX_OUTPUT = int(os.getenv("AI_MAX_OUTPUT", "1200"))
HISTORY_ITEMS = int(os.getenv("AI_HISTORY_ITEMS", "8"))
TIMEOUT = float(os.getenv("AI_TIMEOUT", "35"))

# Short in-process memory. It is intentionally bounded.
_HISTORY: Dict[int, Deque[Tuple[str, str]]] = defaultdict(lambda: deque(maxlen=HISTORY_ITEMS))
_LOCKS: Dict[int, asyncio.Lock] = defaultdict(asyncio.Lock)


def clear_history(user_id: int) -> None:
    _HISTORY.pop(user_id, None)


def enabled_providers() -> List[str]:
    providers = []
    if os.getenv("GEMINI_API_KEY"):
        providers.append("Gemini")
    if os.getenv("GROQ_API_KEY"):
        providers.append("Groq")
    if os.getenv("CEREBRAS_API_KEY"):
        providers.append("Cerebras")
    if os.getenv("CLOUDFLARE_ACCOUNT_ID") and os.getenv("CLOUDFLARE_AUTH_TOKEN"):
        providers.append("Cloudflare")
    if os.getenv("OPENROUTER_API_KEY"):
        providers.append("OpenRouter")
    return providers


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
            data = {"raw": response.text[:1000]}
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
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(item.get("text", ""))
        content = "".join(parts)
    if not content:
        raise RuntimeError("Provider returned an empty answer")
    return str(content).strip()


async def _gemini(user_id: int, prompt: str) -> str:
    key = os.environ["GEMINI_API_KEY"]
    model = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

    contents = []
    for role, content in _HISTORY[user_id]:
        contents.append({"role": "model" if role == "assistant" else "user", "parts": [{"text": content}]})
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


async def _openai_compatible(name: str, user_id: int, *, key_env: str, url: str, model_env: str, default_model: str, extra_headers=None) -> str:
    key = os.environ[key_env]
    model = os.getenv(model_env, default_model)
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    if extra_headers:
        headers.update(extra_headers)
    payload = {
        "model": model,
        "messages": _messages(user_id, _CURRENT_PROMPT.get()),
        "max_tokens": MAX_OUTPUT,
        "temperature": 0.6,
    }
    status, data = await _post_json(url, headers=headers, json=payload)
    if status >= 400:
        raise RuntimeError(f"{name} HTTP {status}: {str(data)[:900]}")
    return _extract_openai(data)


# Small request-local bridge for the generic OpenAI-compatible function.
_CURRENT_PROMPT: Dict[int, str] = {}


async def _groq(user_id: int, prompt: str) -> str:
    _CURRENT_PROMPT[user_id] = prompt
    try:
        return await _openai_compatible(
            "Groq", user_id,
            key_env="GROQ_API_KEY",
            url=os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1") + "/chat/completions",
            model_env="GROQ_MODEL",
            default_model="llama-3.3-70b-versatile",
        )
    finally:
        _CURRENT_PROMPT.pop(user_id, None)


async def _cerebras(user_id: int, prompt: str) -> str:
    _CURRENT_PROMPT[user_id] = prompt
    try:
        return await _openai_compatible(
            "Cerebras", user_id,
            key_env="CEREBRAS_API_KEY",
            url="https://api.cerebras.ai/v1/chat/completions",
            model_env="CEREBRAS_MODEL",
            default_model="gpt-oss-120b",
        )
    finally:
        _CURRENT_PROMPT.pop(user_id, None)


async def _openrouter(user_id: int, prompt: str) -> str:
    _CURRENT_PROMPT[user_id] = prompt
    try:
        return await _openai_compatible(
            "OpenRouter", user_id,
            key_env="OPENROUTER_API_KEY",
            url="https://openrouter.ai/api/v1/chat/completions",
            model_env="OPENROUTER_MODEL",
            default_model="openrouter/free",
            extra_headers={"X-Title": "Rooze Ziba"},
        )
    finally:
        _CURRENT_PROMPT.pop(user_id, None)


async def _cloudflare(user_id: int, prompt: str) -> str:
    account = os.environ["CLOUDFLARE_ACCOUNT_ID"]
    token = os.environ["CLOUDFLARE_AUTH_TOKEN"]
    model = os.getenv("CLOUDFLARE_MODEL", "@cf/meta/llama-3.2-3b-instruct")
    url = f"https://api.cloudflare.com/client/v4/accounts/{account}/ai/run/{model}"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    payload = {"messages": _messages(user_id, prompt), "max_tokens": MAX_OUTPUT}
    status, data = await _post_json(url, headers=headers, json=payload)
    if status >= 400 or not data.get("success", True):
        raise RuntimeError(f"Cloudflare HTTP {status}: {str(data)[:900]}")
    result = data.get("result") or {}
    text = result.get("response") or result.get("text")
    if not text:
        raise RuntimeError(f"Cloudflare empty response: {str(data)[:900]}")
    return str(text).strip()


async def ask_ai(user_id: int, prompt: str) -> tuple[str, str]:
    """Return (answer, provider). Raises RuntimeError if all providers fail."""
    prompt = (prompt or "").strip()
    if not prompt:
        raise RuntimeError("پیام خالی است")
    if len(prompt) > MAX_INPUT:
        prompt = prompt[:MAX_INPUT]

    providers = []
    if os.getenv("GEMINI_API_KEY"):
        providers.append(("Gemini", _gemini))
    if os.getenv("GROQ_API_KEY"):
        providers.append(("Groq", _groq))
    if os.getenv("CEREBRAS_API_KEY"):
        providers.append(("Cerebras", _cerebras))
    if os.getenv("CLOUDFLARE_ACCOUNT_ID") and os.getenv("CLOUDFLARE_AUTH_TOKEN"):
        providers.append(("Cloudflare", _cloudflare))
    if os.getenv("OPENROUTER_API_KEY"):
        providers.append(("OpenRouter", _openrouter))

    if not providers:
        raise RuntimeError("هیچ سرویس AI تنظیم نشده است. حداقل یک API Key در Render قرار بده.")

    errors = []
    async with _LOCKS[user_id]:
        for name, fn in providers:
            try:
                answer = await fn(user_id, prompt)
                if answer:
                    _save_turn(user_id, prompt, answer)
                    return answer, name
            except Exception as exc:
                msg = str(exc).replace("\n", " ")[:500]
                errors.append(f"{name}: {msg}")
                logger.warning("AI provider failed: %s", msg)
                await asyncio.sleep(0.15)

    raise RuntimeError("\n".join(errors) if errors else "هیچ سرویس AI پاسخ نداد.")

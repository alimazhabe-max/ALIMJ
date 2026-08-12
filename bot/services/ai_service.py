"""Free AI service for ALIMJ: Gemini first, Groq as automatic fallback.

No OpenAI SDK is required. API keys are read only from environment variables.
"""
from __future__ import annotations

import asyncio
from typing import Dict, List, Tuple

import httpx

from bot.config import config
from bot.logger import logger

SYSTEM_PROMPT = (
    "تو دستیار هوشمند ربات ALIMJ هستی. پاسخ‌ها را دقیق، مفید و طبیعی بده. "
    "زبان پیش‌فرض فارسی است، مگر کاربر زبان دیگری بخواهد. اگر اطلاعاتی قطعی نیست، "
    "شفاف بگو که مطمئن نیستی و حدس را به‌عنوان واقعیت بیان نکن."
)


def _history(context) -> List[Dict[str, str]]:
    items = context.user_data.get("ai_history", [])
    if not isinstance(items, list):
        return []
    return items[-max(0, config.AI_HISTORY_ITEMS):]


def clear_history(context) -> None:
    context.user_data.pop("ai_history", None)


def _append_history(context, user_text: str, answer: str) -> None:
    items = _history(context)
    items.extend([
        {"role": "user", "content": user_text},
        {"role": "assistant", "content": answer},
    ])
    context.user_data["ai_history"] = items[-max(2, config.AI_HISTORY_ITEMS):]


def active_providers() -> List[str]:
    providers = []
    if config.GEMINI_API_KEY:
        providers.append("Gemini")
    if config.GROQ_API_KEY:
        providers.append("Groq")
    return providers


def _gemini_parts(history: List[Dict[str, str]], user_text: str) -> List[Dict]:
    contents = []
    for item in history:
        role = "user" if item.get("role") == "user" else "model"
        text = str(item.get("content", ""))[: config.AI_MAX_INPUT]
        if text:
            contents.append({"role": role, "parts": [{"text": text}]})
    contents.append({"role": "user", "parts": [{"text": user_text}]})
    return contents


async def _call_gemini(history: List[Dict[str, str]], user_text: str) -> str:
    url = (
        f"{config.GEMINI_BASE_URL.rstrip('/')}/models/"
        f"{config.GEMINI_MODEL}:generateContent"
        f"?key={config.GEMINI_API_KEY}"
    )
    payload = {
        "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": _gemini_parts(history, user_text),
        "generationConfig": {
            "maxOutputTokens": config.AI_MAX_OUTPUT,
        },
    }
    async with httpx.AsyncClient(timeout=config.AI_TIMEOUT) as client:
        response = await client.post(url, json=payload)
        if response.status_code >= 400:
            raise RuntimeError(f"Gemini HTTP {response.status_code}: {response.text[:600]}")
        data = response.json()
    try:
        return data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(f"Gemini response format invalid: {str(data)[:800]}") from exc


async def _call_groq(history: List[Dict[str, str]], user_text: str) -> str:
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(history)
    messages.append({"role": "user", "content": user_text})
    payload = {
        "model": config.GROQ_MODEL,
        "messages": messages,
        "max_tokens": config.AI_MAX_OUTPUT,
        "temperature": 0.7,
    }
    headers = {
        "Authorization": f"Bearer {config.GROQ_API_KEY}",
        "Content-Type": "application/json",
    }
    url = f"{config.GROQ_BASE_URL.rstrip('/')}/chat/completions"
    async with httpx.AsyncClient(timeout=config.AI_TIMEOUT) as client:
        response = await client.post(url, headers=headers, json=payload)
        if response.status_code >= 400:
            raise RuntimeError(f"Groq HTTP {response.status_code}: {response.text[:600]}")
        data = response.json()
    try:
        return data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(f"Groq response format invalid: {str(data)[:800]}") from exc


async def ask_ai(context, user_text: str) -> Tuple[str, str]:
    """Ask Gemini first, then Groq if Gemini fails.

    Returns (answer, provider_name).
    """
    if not user_text or not user_text.strip():
        return "❌ لطفاً سؤال یا درخواستت را بنویس.", "none"
    user_text = user_text.strip()[: config.AI_MAX_INPUT]
    history = _history(context)

    providers = []
    if config.GEMINI_API_KEY:
        providers.append(("Gemini", _call_gemini))
    if config.GROQ_API_KEY:
        providers.append(("Groq", _call_groq))

    if not providers:
        return (
            "❌ هیچ سرویس AI فعال نیست.\n\n"
            "در Render حداقل یکی از این کلیدها را اضافه کن:\n"
            "GEMINI_API_KEY\n"
            "یا\n"
            "GROQ_API_KEY",
            "none",
        )

    errors = []
    for provider_name, fn in providers:
        try:
            answer = await fn(history, user_text)
            if not answer:
                raise RuntimeError("empty response")
            _append_history(context, user_text, answer)
            return answer, provider_name
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            msg = str(exc)
            errors.append(f"{provider_name}: {msg[:220]}")
            logger.warning("AI provider %s failed: %s", provider_name, msg[:500])
            continue

    return (
        "❌ فعلاً هیچ‌کدام از سرویس‌های AI پاسخ ندادند.\n\n"
        "موارد بررسی‌شده:\n- " + "\n- ".join(errors[:4]),
        "none",
    )

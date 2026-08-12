import os
import asyncio
from typing import Dict, List, Optional

import httpx

from bot.logger import logger

DEEPSEEK_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/") + "/chat/completions"
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "").strip()
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash").strip()
AI_MAX_INPUT = int(os.getenv("AI_MAX_INPUT", "5000"))
AI_MAX_OUTPUT = int(os.getenv("AI_MAX_OUTPUT", "1500"))
AI_HISTORY_ITEMS = int(os.getenv("AI_HISTORY_ITEMS", "8"))
AI_TIMEOUT = float(os.getenv("AI_TIMEOUT", "45"))

SYSTEM_PROMPT = """تو دستیار هوشمند ربات تلگرام ALIMJ هستی.
همیشه فارسی روان، محترمانه و کاربردی پاسخ بده، مگر کاربر زبان دیگری بخواهد.
پاسخ‌ها را تا حد امکان منظم و کوتاه بده.
اطلاعاتی مثل قیمت، آب‌وهوا، زمان و اخبار را بدون ابزار زنده قطعی فرض نکن.
اگر مطمئن نیستی، صادقانه بگو.
از ادعای دسترسی به اطلاعات خصوصی کاربر خودداری کن.
"""


def _trim_history(history: List[dict]) -> List[dict]:
    if AI_HISTORY_ITEMS <= 0:
        return []
    return history[-AI_HISTORY_ITEMS:]


def reset_history(user_data: dict) -> None:
    user_data.pop("deepseek_history", None)


def _extract_content(data: dict) -> str:
    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError("DeepSeek پاسخ قابل استفاده‌ای برنگرداند.")
    message = choices[0].get("message") or {}
    content = message.get("content")
    if not content:
        raise RuntimeError("پاسخ DeepSeek خالی بود.")
    return str(content).strip()


async def ask_deepseek(user_text: str, history: Optional[List[dict]] = None, user_name: str = "کاربر", city: str = "") -> tuple[str, List[dict]]:
    if not DEEPSEEK_API_KEY:
        raise RuntimeError("DEEPSEEK_API_KEY در Environment Variables تنظیم نشده است.")

    text = (user_text or "").strip()
    if not text:
        raise ValueError("پیام خالی است.")
    if len(text) > AI_MAX_INPUT:
        text = text[:AI_MAX_INPUT]

    history = _trim_history(history or [])
    context = SYSTEM_PROMPT
    if user_name:
        context += f"\nنام نمایشی کاربر: {user_name}"
    if city:
        context += f"\nشهر ثبت‌شده کاربر: {city}"

    messages = [{"role": "system", "content": context}] + history + [{"role": "user", "content": text}]
    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": messages,
        "stream": False,
        "temperature": 0.7,
        "max_tokens": AI_MAX_OUTPUT,
    }
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json",
    }

    last_error = None
    for attempt in range(2):
        try:
            timeout = httpx.Timeout(AI_TIMEOUT, connect=15.0)
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(DEEPSEEK_URL, headers=headers, json=payload)

            if response.status_code == 401:
                raise RuntimeError("کلید DeepSeek نامعتبر است یا دسترسی API ندارد.")
            if response.status_code == 402:
                raise RuntimeError("اعتبار حساب DeepSeek کافی نیست.")
            if response.status_code == 429:
                last_error = RuntimeError("محدودیت موقت درخواست DeepSeek (429).")
                if attempt == 0:
                    await asyncio.sleep(1.5)
                    continue
                raise last_error
            if response.status_code >= 500:
                last_error = RuntimeError(f"خطای سرور DeepSeek ({response.status_code}).")
                if attempt == 0:
                    await asyncio.sleep(1.0)
                    continue
                raise last_error
            if response.status_code >= 400:
                detail = response.text[:400]
                raise RuntimeError(f"خطای DeepSeek ({response.status_code}): {detail}")

            data = response.json()
            answer = _extract_content(data)

            new_history = history + [
                {"role": "user", "content": text},
                {"role": "assistant", "content": answer},
            ]
            return answer, _trim_history(new_history)

        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            last_error = exc
            if attempt == 0:
                await asyncio.sleep(1.0)
                continue
            break
        except Exception as exc:
            logger.error(f"DeepSeek request failed: {exc}")
            raise

    logger.error(f"DeepSeek unavailable: {last_error}")
    raise RuntimeError("ارتباط با DeepSeek برقرار نشد. چند لحظه بعد دوباره امتحان کن.")

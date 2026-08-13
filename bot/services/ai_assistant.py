"""
دستیار هوشمند — انتخاب مدل توسط کاربر + کیبورد شیشه‌ای (Inline)

مسیر پیشنهادی فایل:  bot/features/ai_assistant.py

قابلیت‌ها:
  • لیست مدل‌های رایگان (OpenRouter / Groq / Gemini / Mistral / Cerebras)
  • کیبورد شیشه‌ای زیر پیام برای انتخاب مدل (با تیک ✅ روی مدل فعلی)
  • ذخیره‌ی انتخاب هر کاربر در فایل JSON (بدون نیاز به تغییر دیتابیس)
  • حافظه‌ی گفتگو برای هر کاربر (۱۲ پیام آخر) و دکمه‌ی پاک‌کردن حافظه
  • اگر مدل انتخابی جواب نداد، خودکار به مدل‌های دیگر fallback می‌کند
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any

import httpx
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

# ---------------------------------------------------------------- تنظیمات

DATA_FILE = Path(os.getenv("AI_MODELS_STORE", "data/ai_user_models.json"))
HISTORY_LIMIT = 12          # تعداد پیام‌های نگهداری‌شده در حافظه‌ی هر کاربر
REQUEST_TIMEOUT = 90        # ثانیه

SYSTEM_PROMPT = (
    "تو دستیار هوشمند ربات «روز زیبا» هستی. "
    "پاسخ‌ها را کوتاه، دقیق، دوستانه و به زبان فارسی روان بده. "
    "اگر کاربر به زبان دیگری نوشت، به همان زبان جواب بده."
)

# ------------------------------------------------------ فهرست مدل‌ها (رایگان)
# هر مدل: (کلید، نام نمایشی، provider، model_id)
MODELS: dict[str, dict[str, str]] = {
    "auto": {
        "label": "⚡️ خودکار (بهترین موجود)",
        "provider": "auto",
        "model": "",
        "note": "اولین سرویس در دسترس را انتخاب می‌کند",
    },
    # ---- Groq (رایگان و بسیار سریع)
    "groq_llama70b": {
        "label": "🦙 Llama 3.3 70B — Groq",
        "provider": "groq",
        "model": "llama-3.3-70b-versatile",
        "note": "سریع‌ترین گزینه، عمومی",
    },
    "groq_llama8b": {
        "label": "🐣 Llama 3.1 8B — Groq",
        "provider": "groq",
        "model": "llama-3.1-8b-instant",
        "note": "خیلی سریع، سبک",
    },
    # ---- Google Gemini (رایگان)
    "gemini_flash": {
        "label": "✨ Gemini 2.0 Flash — Google",
        "provider": "gemini",
        "model": "gemini-2.0-flash",
        "note": "متعادل و باهوش",
    },
    "gemini_flash_lite": {
        "label": "💨 Gemini Flash Lite — Google",
        "provider": "gemini",
        "model": "gemini-2.0-flash-lite",
        "note": "سبک و کم‌مصرف",
    },
    # ---- OpenRouter (مدل‌های :free)
    "or_deepseek": {
        "label": "🧠 DeepSeek V3 — OpenRouter",
        "provider": "openrouter",
        "model": "deepseek/deepseek-chat-v3-0324:free",
        "note": "قوی در استدلال و کدنویسی",
    },
    "or_qwen": {
        "label": "🐉 Qwen 2.5 72B — OpenRouter",
        "provider": "openrouter",
        "model": "qwen/qwen-2.5-72b-instruct:free",
        "note": "چندزبانه و دقیق",
    },
    "or_llama_vision": {
        "label": "🖼 Llama 3.2 Vision — OpenRouter",
        "provider": "openrouter",
        "model": "meta-llama/llama-3.2-11b-vision-instruct:free",
        "note": "متن + تصویر",
    },
    # ---- Mistral (رایگان)
    "mistral_small": {
        "label": "🌬 Mistral Small — Mistral AI",
        "provider": "mistral",
        "model": "mistral-small-latest",
        "note": "خلاصه‌سازی و نگارش",
    },
    # ---- Cerebras (رایگان و فوق‌سریع)
    "cerebras_llama": {
        "label": "🚀 Llama 3.3 70B — Cerebras",
        "provider": "cerebras",
        "model": "llama-3.3-70b",
        "note": "سرعت بسیار بالا",
    },
}

DEFAULT_MODEL = "auto"

ENV_KEYS = {
    "groq": "GROQ_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "mistral": "MISTRAL_API_KEY",
    "cerebras": "CEREBRAS_API_KEY",
}


def _key(provider: str) -> str | None:
    name = ENV_KEYS.get(provider)
    if not name:
        return None
    val = os.getenv(name)
    return val.strip() if val else None


def provider_available(provider: str) -> bool:
    if provider == "auto":
        return any(_key(p) for p in ENV_KEYS)
    return bool(_key(provider))


def available_models() -> list[str]:
    return [k for k, m in MODELS.items() if provider_available(m["provider"])]


# ------------------------------------------------------------- ذخیره‌سازی

def _load_store() -> dict[str, Any]:
    try:
        return json.loads(DATA_FILE.read_text("utf-8"))
    except Exception:
        return {}


def _save_store(data: dict[str, Any]) -> None:
    try:
        DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
        DATA_FILE.write_text(json.dumps(data, ensure_ascii=False), "utf-8")
    except Exception:
        pass


def get_user_model(user_id: int) -> str:
    key = _load_store().get(str(user_id), DEFAULT_MODEL)
    return key if key in MODELS else DEFAULT_MODEL


def set_user_model(user_id: int, model_key: str) -> None:
    if model_key not in MODELS:
        return
    data = _load_store()
    data[str(user_id)] = model_key
    _save_store(data)


def model_label(user_id: int) -> str:
    return MODELS[get_user_model(user_id)]["label"]


# ------------------------------------------------------------ حافظه گفتگو

_HISTORY: dict[int, list[dict[str, str]]] = {}


def get_history(user_id: int) -> list[dict[str, str]]:
    return _HISTORY.setdefault(user_id, [])


def push_history(user_id: int, role: str, content: str) -> None:
    h = get_history(user_id)
    h.append({"role": role, "content": content})
    del h[:-HISTORY_LIMIT]


def clear_memory(user_id: int) -> None:
    _HISTORY.pop(user_id, None)


# ------------------------------------------------- کیبورد شیشه‌ای (Inline)

def get_ai_keyboard(user_id: int) -> InlineKeyboardMarkup:
    """کیبورد شیشه‌ای اصلی دستیار هوشمند."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(f"🧩 مدل: {model_label(user_id)}", callback_data="ai_models")],
            [
                InlineKeyboardButton("🧹 پاک کردن حافظه", callback_data="ai_clear_memory"),
                InlineKeyboardButton("❓ راهنما", callback_data="ai_help"),
            ],
        ]
    )


def get_models_keyboard(user_id: int) -> InlineKeyboardMarkup:
    """کیبورد شیشه‌ای انتخاب مدل — دو ستونه، با تیک روی مدل فعلی."""
    current = get_user_model(user_id)
    rows: list[list[InlineKeyboardButton]] = []
    buf: list[InlineKeyboardButton] = []

    for key, m in MODELS.items():
        ok = provider_available(m["provider"])
        mark = "✅ " if key == current else ("" if ok else "🔒 ")
        btn = InlineKeyboardButton(
            f"{mark}{m['label']}",
            callback_data=f"ai_set:{key}" if ok else "ai_locked",
        )
        if key == "auto":
            rows.append([btn])
            continue
        buf.append(btn)
        if len(buf) == 1:  # نام مدل‌ها بلند است → یک‌ستونه خواناتر است
            rows.append(buf)
            buf = []
    if buf:
        rows.append(buf)

    rows.append([InlineKeyboardButton("🔙 بازگشت", callback_data="ai_home")])
    return InlineKeyboardMarkup(rows)


def ai_intro_text(user_id: int) -> str:
    m = MODELS[get_user_model(user_id)]
    online = [MODELS[k]["label"] for k in available_models() if k != "auto"]
    return (
        "🤖 <b>دستیار هوشمند روز زیبا</b>\n"
        "─────────────────\n"
        f"🧩 مدل فعلی: <b>{m['label']}</b>\n"
        f"💡 {m.get('note', '')}\n"
        f"🟢 مدل‌های در دسترس: <b>{len(online)}</b>\n"
        "─────────────────\n"
        "پیامت را بنویس و بفرست تا جواب بگیری.\n"
        "برای تغییر مدل، دکمه‌ی «🧩 مدل» را بزن.\n"
        "خروج: «🔙 بازگشت»"
    )


# ------------------------------------------------------------- فراخوانی AI

async def _chat_openai_style(
    url: str, api_key: str, model: str, messages: list[dict[str, str]], extra_headers: dict | None = None
) -> str:
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    if extra_headers:
        headers.update(extra_headers)
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        r = await client.post(
            url,
            headers=headers,
            json={"model": model, "messages": messages, "temperature": 0.7},
        )
        r.raise_for_status()
        data = r.json()
    return (data["choices"][0]["message"]["content"] or "").strip()


async def _chat_gemini(api_key: str, model: str, messages: list[dict[str, str]]) -> str:
    contents = [
        {
            "role": "model" if m["role"] == "assistant" else "user",
            "parts": [{"text": m["content"]}],
        }
        for m in messages
        if m["role"] != "system"
    ]
    body = {
        "contents": contents,
        "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
    }
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        r = await client.post(url, params={"key": api_key}, json=body)
        r.raise_for_status()
        data = r.json()
    parts = data["candidates"][0]["content"]["parts"]
    return "".join(p.get("text", "") for p in parts).strip()


async def _call_provider(provider: str, model: str, messages: list[dict[str, str]]) -> str:
    api_key = _key(provider)
    if not api_key:
        raise RuntimeError(f"کلید {provider} تنظیم نشده است")

    if provider == "groq":
        return await _chat_openai_style(
            "https://api.groq.com/openai/v1/chat/completions", api_key, model, messages
        )
    if provider == "openrouter":
        return await _chat_openai_style(
            "https://openrouter.ai/api/v1/chat/completions",
            api_key,
            model,
            messages,
            {"HTTP-Referer": "https://t.me", "X-Title": "Rooz Ziba Bot"},
        )
    if provider == "mistral":
        return await _chat_openai_style(
            "https://api.mistral.ai/v1/chat/completions", api_key, model, messages
        )
    if provider == "cerebras":
        return await _chat_openai_style(
            "https://api.cerebras.ai/v1/chat/completions", api_key, model, messages
        )
    if provider == "gemini":
        return await _chat_gemini(api_key, model, messages)
    raise RuntimeError(f"سرویس ناشناخته: {provider}")


def _fallback_order(selected: str) -> list[str]:
    """ترتیب تلاش: مدل انتخابی، سپس بقیه‌ی مدل‌های در دسترس."""
    order = [] if selected == "auto" else [selected]
    for k in available_models():
        if k != "auto" and k not in order:
            order.append(k)
    return order


async def ask_ai_selected(user_id: int, text: str) -> tuple[str, str]:
    """پرسش از مدل انتخابی کاربر. خروجی: (پاسخ، نام مدل)"""
    selected = get_user_model(user_id)
    candidates = _fallback_order(selected)
    if not candidates:
        raise RuntimeError(
            "هیچ سرویس هوش مصنوعی فعالی پیدا نشد. یکی از کلیدهای زیر را در .env بگذار:\n"
            + "، ".join(ENV_KEYS.values())
        )

    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + get_history(user_id)
    messages.append({"role": "user", "content": text})

    errors: list[str] = []
    for key in candidates:
        m = MODELS[key]
        try:
            answer = await _call_provider(m["provider"], m["model"], messages)
            if answer:
                push_history(user_id, "user", text)
                push_history(user_id, "assistant", answer)
                return answer, m["label"]
            errors.append(f"{m['label']}: پاسخ خالی")
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{m['label']}: {str(exc)[:120]}")
    raise RuntimeError("هیچ مدلی پاسخ نداد:\n" + "\n".join(errors[:5]))


# --------------------------------------------------- هندلر کیبورد شیشه‌ای

async def ai_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """هندلر دکمه‌های شیشه‌ای دستیار هوشمند (pattern=^ai_)."""
    q = update.callback_query
    if not q:
        return
    user_id = q.from_user.id
    data = q.data or ""

    try:
        if data == "ai_models":
            await q.answer()
            await q.edit_message_text(
                "🧩 <b>انتخاب مدل هوش مصنوعی</b>\n"
                "مدلی که می‌خواهی با آن گفتگو کنی را انتخاب کن.\n"
                "🔒 یعنی کلید آن سرویس هنوز تنظیم نشده.",
                parse_mode="HTML",
                reply_markup=get_models_keyboard(user_id),
            )
            return

        if data.startswith("ai_set:"):
            key = data.split(":", 1)[1]
            if key not in MODELS:
                await q.answer("مدل نامعتبر", show_alert=True)
                return
            set_user_model(user_id, key)
            clear_memory(user_id)
            await q.answer(f"✅ {MODELS[key]['label']} انتخاب شد")
            await q.edit_message_text(
                "🧩 <b>انتخاب مدل هوش مصنوعی</b>\n"
                f"مدل فعلی: <b>{MODELS[key]['label']}</b>\n"
                f"💡 {MODELS[key].get('note', '')}",
                parse_mode="HTML",
                reply_markup=get_models_keyboard(user_id),
            )
            return

        if data == "ai_locked":
            await q.answer("🔒 کلید این سرویس تنظیم نشده است.", show_alert=True)
            return

        if data == "ai_clear_memory":
            clear_memory(user_id)
            await q.answer("🧹 حافظه‌ی گفتگو پاک شد")
            return

        if data == "ai_help":
            await q.answer()
            await q.edit_message_text(
                "❓ <b>راهنمای دستیار هوشمند</b>\n\n"
                "• هر پیامی بفرستی، جواب می‌گیری.\n"
                "• دستیار ۱۲ پیام آخر را به یاد دارد.\n"
                "• با «🧩 مدل» می‌توانی مدل را عوض کنی.\n"
                "• با «🧹 پاک کردن حافظه» گفتگو از نو شروع می‌شود.\n"
                "• برای خروج، «🔙 بازگشت» را بفرست.",
                parse_mode="HTML",
                reply_markup=get_ai_keyboard(user_id),
            )
            return

        if data == "ai_home":
            await q.answer()
            await q.edit_message_text(
                ai_intro_text(user_id),
                parse_mode="HTML",
                reply_markup=get_ai_keyboard(user_id),
            )
            return
    except Exception:
        try:
            await q.answer()
        except Exception:
            pass

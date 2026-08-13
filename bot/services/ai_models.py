"""کاتالوگ مدل‌های هوش مصنوعی + انتخاب مدل توسط کاربر (روز زیبا)

مسیر فایل: bot/services/ai_models.py

- همه مدل‌ها رایگان هستند (Free tier)
- انتخاب هر کاربر در data/ai_user_models.json ذخیره می‌شود
- کیبورد شیشه‌ای (Inline) برای انتخاب مدل ساخته می‌شود
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Dict, List, Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

# ---------------------------------------------------------------- catalog

# provider: کلید داخلی سرویس‌دهنده  |  model: نام مدل نزد سرویس‌دهنده
MODELS: List[dict] = [
    # Google Gemini — رایگان و سریع
    {"id": "gemini_flash",   "name": "Gemini 2.0 Flash",      "icon": "💎", "provider": "gemini",     "model": "gemini-2.0-flash"},
    {"id": "gemini_lite",    "name": "Gemini Flash Lite",     "icon": "💠", "provider": "gemini",     "model": "gemini-2.0-flash-lite"},
    # Groq — سریع‌ترین
    {"id": "groq_llama70",   "name": "Llama 3.3 70B",         "icon": "⚡️", "provider": "groq",       "model": "llama-3.3-70b-versatile"},
    {"id": "groq_llama8",    "name": "Llama 3.1 8B (سریع)",   "icon": "🚀", "provider": "groq",       "model": "llama-3.1-8b-instant"},
    # Cerebras
    {"id": "cerebras_oss",   "name": "GPT-OSS 120B",          "icon": "🧠", "provider": "cerebras",   "model": "gpt-oss-120b"},
    # OpenRouter — مدل‌های رایگان
    {"id": "or_deepseek",    "name": "DeepSeek V3",           "icon": "🐋", "provider": "openrouter", "model": "deepseek/deepseek-chat-v3-0324:free"},
    {"id": "or_qwen",        "name": "Qwen 2.5 72B",          "icon": "🀄️", "provider": "openrouter", "model": "qwen/qwen-2.5-72b-instruct:free"},
    {"id": "or_mistral",     "name": "Mistral Small",         "icon": "🌀", "provider": "openrouter", "model": "mistralai/mistral-small-3.2-24b-instruct:free"},
    # Cloudflare Workers AI
    {"id": "cf_llama",       "name": "CF Llama 3.2",          "icon": "☁️", "provider": "cloudflare", "model": "@cf/meta/llama-3.2-3b-instruct"},
]

PROVIDER_LABEL = {
    "gemini": "Gemini",
    "groq": "Groq",
    "cerebras": "Cerebras",
    "openrouter": "OpenRouter",
    "cloudflare": "Cloudflare",
}

AUTO_ID = "auto"


def provider_available(provider: str) -> bool:
    """آیا کلید این سرویس‌دهنده تنظیم شده؟"""
    if provider == "gemini":
        return bool(os.getenv("GEMINI_API_KEY"))
    if provider == "groq":
        return bool(os.getenv("GROQ_API_KEY"))
    if provider == "cerebras":
        return bool(os.getenv("CEREBRAS_API_KEY"))
    if provider == "openrouter":
        return bool(os.getenv("OPENROUTER_API_KEY"))
    if provider == "cloudflare":
        return bool(os.getenv("CLOUDFLARE_ACCOUNT_ID") and os.getenv("CLOUDFLARE_AUTH_TOKEN"))
    return False


def available_models() -> List[dict]:
    return [m for m in MODELS if provider_available(m["provider"])]


def available_providers() -> List[str]:
    seen = []
    for m in MODELS:
        if provider_available(m["provider"]) and m["provider"] not in seen:
            seen.append(m["provider"])
    return seen


def find_model(model_id: Optional[str]) -> Optional[dict]:
    if not model_id or model_id == AUTO_ID:
        return None
    for m in MODELS:
        if m["id"] == model_id:
            return m
    return None


# ---------------------------------------------------------------- storage

_LOCK = threading.Lock()


def _store_path() -> Path:
    base = os.getenv("DATA_DIR") or "data"
    db_path = os.getenv("DB_PATH")
    if db_path:
        base = str(Path(db_path).parent)
    elif Path("/data").is_dir() and os.access("/data", os.W_OK):
        base = "/data"
    p = Path(base)
    try:
        p.mkdir(parents=True, exist_ok=True)
    except Exception:
        p = Path(".")
    return p / "ai_user_models.json"


def _load() -> Dict[str, str]:
    try:
        with open(_store_path(), "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save(data: Dict[str, str]) -> None:
    try:
        with open(_store_path(), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
    except Exception:
        pass


def get_user_model_id(user_id: int) -> str:
    with _LOCK:
        return _load().get(str(user_id), AUTO_ID)


def set_user_model_id(user_id: int, model_id: str) -> None:
    with _LOCK:
        data = _load()
        data[str(user_id)] = model_id
        _save(data)


def get_user_model(user_id: int) -> Optional[dict]:
    """مدل انتخابی کاربر؛ اگر خودکار یا غیرفعال بود None."""
    m = find_model(get_user_model_id(user_id))
    if m and provider_available(m["provider"]):
        return m
    return None


def current_model_title(user_id: int) -> str:
    m = get_user_model(user_id)
    if not m:
        return "🎯 خودکار (بهترین سرویس در دسترس)"
    return f"{m['icon']} {m['name']} — {PROVIDER_LABEL[m['provider']]}"


# ---------------------------------------------------------------- keyboards

def models_keyboard(user_id: int) -> InlineKeyboardMarkup:
    """کیبورد شیشه‌ای انتخاب مدل."""
    selected = get_user_model_id(user_id)
    rows: List[List[InlineKeyboardButton]] = [[
        InlineKeyboardButton(
            ("✅ " if selected == AUTO_ID else "") + "🎯 خودکار (پیشنهادی)",
            callback_data=f"ai_set:{AUTO_ID}",
        )
    ]]

    row: List[InlineKeyboardButton] = []
    for m in MODELS:
        ok = provider_available(m["provider"])
        mark = "✅ " if (selected == m["id"] and ok) else ("" if ok else "🔒 ")
        row.append(InlineKeyboardButton(
            f"{mark}{m['icon']} {m['name']}",
            callback_data=f"ai_set:{m['id']}" if ok else "ai_locked",
        ))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)

    rows.append([
        InlineKeyboardButton("🧹 پاک کردن حافظه", callback_data="ai_clear_memory"),
        InlineKeyboardButton("🔙 خروج", callback_data="ai_exit"),
    ])
    return InlineKeyboardMarkup(rows)


def assistant_keyboard(user_id: int) -> InlineKeyboardMarkup:
    """کیبورد شیشه‌ای زیر پاسخ‌های دستیار."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎛 انتخاب مدل هوش مصنوعی", callback_data="ai_models")],
        [
            InlineKeyboardButton("🧹 پاک کردن حافظه", callback_data="ai_clear_memory"),
            InlineKeyboardButton("🔙 خروج", callback_data="ai_exit"),
        ],
    ])


def assistant_intro(user_id: int) -> str:
    provs = [PROVIDER_LABEL[p] for p in available_providers()]
    return (
        "🤖 <b>دستیار هوشمند روز زیبا</b>\n\n"
        f"مدل فعلی: <b>{current_model_title(user_id)}</b>\n"
        f"سرویس‌های فعال: {'، '.join(provs) if provs else 'هیچ‌کدام ❗️'}\n\n"
        "هر سؤالی داری بپرس؛ متن، ترجمه، خلاصه، کد یا ایده.\n"
        "برای تغییر مدل دکمه «🎛 انتخاب مدل» را بزن.\n"
        "برای خروج «🔙 بازگشت» را بفرست."
    )

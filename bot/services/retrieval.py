"""Hybrid retrieval layer for Rooze Ziba.

Combines user memory and the local knowledge base, with optional web retrieval.
The default path is local-only to avoid surprise network calls; web retrieval is
explicitly enabled by the AI tool when freshness/current information is needed.
"""
from __future__ import annotations

import re
from typing import Any

_MAX_CONTEXT = 3200
_MAX_MEMORY = 8
_MAX_KB = 4


def _tokens(text: str) -> set[str]:
    return {
        x.lower() for x in re.findall(r"[\w\u0600-\u06ff]{2,}", text or "")
        if len(x) >= 2
    }


def _looks_current(query: str) -> bool:
    return bool(re.search(
        r"امروز|الان|فعلی|جدیدترین|آخرین|اخبار|قیمت|نرخ|اکنون|today|latest|current|news|price|rate",
        query or "", re.I,
    ))


def retrieve_local(user_id: int, query: str, *, memory_limit: int = _MAX_MEMORY,
                   knowledge_limit: int = _MAX_KB) -> dict[str, Any]:
    """Retrieve only local, user-safe context. Never touches jokes_data.json."""
    from bot.database import get_ai_memory
    from bot.services.knowledge_base import search_knowledge

    memory = get_ai_memory(user_id, limit=memory_limit, query=query) if user_id else []
    knowledge = search_knowledge(query, limit=knowledge_limit)
    return {"memory": memory, "knowledge": knowledge}


def format_context(data: dict[str, Any], query: str = "", *, include_web: bool = False,
                   web_text: str = "") -> str:
    parts: list[str] = []
    memory = data.get("memory") or []
    knowledge = data.get("knowledge") or []
    if memory:
        parts.append("حافظه مرتبط کاربر:\n" + "\n".join(f"- {k}: {v}" for k, v in memory[:_MAX_MEMORY]))
    if knowledge:
        lines = []
        for item in knowledge[:_MAX_KB]:
            lines.append(f"- {item.get('source', 'unknown')}: {item.get('snippet', '')[:700]}")
        parts.append("پایگاه دانش داخلی:\n" + "\n".join(lines))
    if include_web and web_text:
        parts.append("منبع وب (ممکن است زمان‌مند باشد):\n" + web_text[:1200])
    if not parts:
        return ""
    return ("منابع بازیابی‌شده برای این درخواست. فقط از بخش‌های مرتبط استفاده کن؛ "
            "اگر منبع کافی نیست، حدس نزن.\n\n" + "\n\n".join(parts))[:_MAX_CONTEXT]


def build_local_context(user_id: int, query: str) -> str:
    return format_context(retrieve_local(user_id, query), query)


async def hybrid_search(user_id: int, query: str, *, include_web: bool = False) -> str:
    query = (query or "").strip()
    if not query:
        return "عبارت جستجو خالی است."
    data = retrieve_local(user_id, query)
    web_text = ""
    if include_web:
        from bot.services.ai_extras import web_search
        web_text = await web_search(query, max_results=4)
    elif _looks_current(query) and not data["knowledge"]:
        # Do not perform an implicit network request; tell the caller why web may help.
        web_text = "برای اطلاعات زمان‌مند/فعلی، جستجوی وب لازم است."
    return format_context(data, query, include_web=include_web, web_text=web_text) or "منبع مرتبطی پیدا نشد."

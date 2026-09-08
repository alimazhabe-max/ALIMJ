"""Bounded specialist-agent orchestration for Rooze Ziba.

Specialists are intentionally lightweight and deterministic. They reuse the
existing tool registry, so all V3-V22 timeout/cache/concurrency/observability
controls remain in force.
"""
from __future__ import annotations

import asyncio
import re
from typing import Any

MAX_SPECIALISTS = 4
MAX_STEPS_PER_SPECIALIST = 3


def _has(text: str, pattern: str) -> bool:
    return bool(re.search(pattern, text, re.I))


def select_specialists(goal: str) -> list[str]:
    q = (goal or "").strip()
    if not q:
        return []
    names: list[str] = []
    if _has(q, r"هوا|آب\s*و\s*هوا|دما|باران|آلودگی|کیفیت\s*هوا|weather|aqi"):
        names.append("weather")
    if _has(q, r"قیمت|دلار|یورو|طلا|سکه|ارز|کریپتو|بیت.?کوین|بازار|market|price|crypto"):
        names.append("market")
    if _has(q, r"خرید|بخر|محصول|فروشگاه|shopping|لینک\s*خرید"):
        names.append("shopping")
    if _has(q, r"مستندات|راهنما|قابلیت.*ربات|تنظیمات.*ربات|knowledge|documentation|تحقیق|بررسی|خبر|اخبار|وب|اینترنت|research|news"):
        names.append("research")
    if not names:
        names.append("general")
    return names[:MAX_SPECIALISTS]


def build_specialist_plan(name: str, goal: str) -> list[dict[str, Any]]:
    q = (goal or "").strip()
    if name == "weather":
        steps = [{"tool": "get_weather", "arguments": {}}]
        if _has(q, r"آلودگی|کیفیت\s*هوا|aqi"):
            steps.append({"tool": "get_air_quality", "arguments": {}})
        return steps[:MAX_STEPS_PER_SPECIALIST]
    if name == "market":
        return [{"tool": "get_market_prices", "arguments": {}}]
    if name == "shopping":
        return [{"tool": "search_shopping", "arguments": {"query": q, "source": "all", "max_results": 8}}]
    if name == "research":
        if _has(q, r"مستندات|راهنما|قابلیت.*ربات|تنظیمات.*ربات|knowledge|documentation"):
            return [{"tool": "search_knowledge_base", "arguments": {"query": q, "limit": 5}}]
        return [{"tool": "hybrid_retrieve", "arguments": {"query": q, "include_web": True}}]
    return [{"tool": "hybrid_retrieve", "arguments": {"query": q, "include_web": True}}]


async def _run_specialist(name: str, goal: str, user_id: int) -> dict[str, Any]:
    from bot.services.ai_tools import execute_tool, get_registered_tool_names
    from bot.services.agent_learning import record
    available = get_registered_tool_names()
    plan = build_specialist_plan(name, goal)
    results = []
    for step in plan:
        tool = step["tool"]
        if tool not in available:
            results.append({"tool": tool, "ok": False, "error": "tool unavailable"})
            continue
        try:
            value = await execute_tool(tool, step.get("arguments", {}), user_id=user_id)
            text = str(value)[:3000]
            ok = not text.startswith(("خطا در اجرای", "زمان اجرای", "ابزار ناشناخته"))
            record(user_id, name, tool, ok, "tool failure" if not ok else "")
            results.append({"tool": tool, "ok": ok, "result": text})
        except Exception as exc:
            record(user_id, name, tool, False, str(exc)[:500])
            results.append({"tool": tool, "ok": False, "error": str(exc)[:500]})
    return {"agent": name, "results": results}


async def run_multi_agent(goal: str, *, user_id: int = 0) -> str:
    q = (goal or "").strip()
    specialists = select_specialists(q)
    if not specialists:
        return "هدف خالی است."
    # Specialists are independent, so run them concurrently; execute_tool still
    # enforces its global semaphore, timeout, cache and single-flight controls.
    outputs = await asyncio.gather(*(_run_specialist(n, q, user_id) for n in specialists), return_exceptions=True)
    normalized = []
    for name, item in zip(specialists, outputs):
        if isinstance(item, Exception):
            normalized.append({"agent": name, "results": [{"tool": "-", "ok": False, "error": str(item)[:500]}]})
        else:
            normalized.append(item)

    lines = ["🤖 Multi-Agent نتیجه", "", f"🎯 هدف: {q[:500]}", "", "🧩 متخصصان: " + "، ".join(specialists)]
    for item in normalized:
        lines.append(f"\n🔹 {item['agent']}")
        for result in item["results"]:
            if result.get("ok"):
                lines.append(f"• {result['tool']}: {result.get('result', '')[:2200]}")
            else:
                lines.append(f"• {result.get('tool', '-')}: خطا/در دسترس نیست — {result.get('error', 'نامشخص')[:300]}")
    return "\n".join(lines)[:7600]

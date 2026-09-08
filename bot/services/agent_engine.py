"""Bounded autonomous planning and self-repair for Rooze Ziba.

This layer deliberately uses deterministic intent planning rather than an
unbounded LLM loop. It selects existing read-only tools, executes at most a
small number of steps, and can retry a failed step with a safe fallback.
"""
from __future__ import annotations

import re
from typing import Any

from bot.logger import logger

MAX_PLAN_STEPS = 4
import os

MAX_REPAIRS = max(0, min(2, int(os.getenv("AI_AGENT_MAX_REPAIRS", "1"))))


def _current(text: str) -> bool:
    return bool(re.search(r"امروز|الان|فعلی|جدیدترین|آخرین|اخبار|قیمت|نرخ|today|latest|current|news|price|rate", text, re.I))


def _city_from_query(text: str) -> str | None:
    m = re.search(r"(?:هوای|آب\s*و\s*هوای|هوا(?:ی)?|weather\s+)([\w\u0600-\u06ff -]{2,40})", text, re.I)
    if not m:
        return None
    value = m.group(1).strip(" ؟?!،,.:")
    if value and value not in {"امروز", "فردا", "الان", "فعلی"}:
        return value
    return None


def build_plan(goal: str) -> list[dict[str, Any]]:
    """Create a small, explainable plan from the user's goal."""
    q = (goal or "").strip()
    if not q:
        return []
    steps: list[dict[str, Any]] = []
    # Fresh/current requests should go through hybrid retrieval first so that
    # web freshness is available before domain-specific tools are considered.
    if _current(q) and bool(re.search(r"خبر|اخبار|اطلاعات|بررسی|وضعیت|latest|news|current", q, re.I)):
        steps.append({"tool": "hybrid_retrieve", "arguments": {"query": q, "include_web": True}})
        if len(steps) >= MAX_PLAN_STEPS:
            return steps
    weather = bool(re.search(r"هوا|آب\s*و\s*هوا|دما|باران|بارون|weather", q, re.I))
    aqi = bool(re.search(r"کیفیت\s*هوا|آلودگی|aqi", q, re.I))
    market = bool(re.search(r"قیمت|دلار|یورو|طلا|سکه|ارز|کریپتو|بیت.?کوین|market|price", q, re.I))
    knowledge = bool(re.search(r"مستندات|راهنمای ربات|قابلیت.*ربات|تنظیمات.*ربات|knowledge|documentation", q, re.I))
    shopping = bool(re.search(r"خرید|بخر|قیمت.*محصول|لینک.*خرید|فروشگاه|shopping", q, re.I))

    if weather:
        args = {}
        city = _city_from_query(q)
        if city:
            args["city"] = city
        steps.append({"tool": "get_weather", "arguments": args})
        if aqi and len(steps) < MAX_PLAN_STEPS:
            steps.append({"tool": "get_air_quality", "arguments": args})
    if market and len(steps) < MAX_PLAN_STEPS:
        steps.append({"tool": "get_market_prices", "arguments": {}})
    if shopping and len(steps) < MAX_PLAN_STEPS:
        steps.append({"tool": "search_shopping", "arguments": {"query": q, "source": "all", "max_results": 8}})
    if knowledge and len(steps) < MAX_PLAN_STEPS:
        steps.append({"tool": "search_knowledge_base", "arguments": {"query": q, "limit": 5}})
    if not steps and _current(q):
        steps.append({"tool": "hybrid_retrieve", "arguments": {"query": q, "include_web": True}})
    if not steps and re.search(r"اینترنت|وب|جستجو|خبر", q, re.I):
        steps.append({"tool": "web_search", "arguments": {"query": q}})
    return steps[:MAX_PLAN_STEPS]


async def run_agent(goal: str, *, user_id: int = 0) -> str:
    """Plan, execute, and perform one bounded repair attempt."""
    goal = (goal or "").strip()
    if not goal:
        return "هدف خالی است."
    plan = build_plan(goal)
    if not plan:
        return "برای این درخواست برنامه ابزارمحور مطمئنی پیدا نشد؛ پاسخ مستقیم AI مناسب‌تر است."

    from bot.services.ai_tools import execute_tool, get_registered_tool_names
    from bot.services.agent_learning import record, should_prefer_fallback
    available = get_registered_tool_names()
    results: list[dict[str, Any]] = []
    repairs = 0
    for index, step in enumerate(plan, 1):
        tool = step["tool"]
        args = dict(step.get("arguments") or {})
        if tool not in available:
            return f"برنامه متوقف شد: ابزار {tool} در دسترس نیست."
        try:
            effective_tool = tool
            learned_from = None
            fallback_map = {
                "get_weather": "hybrid_retrieve",
                "get_air_quality": "hybrid_retrieve",
                "get_market_prices": "hybrid_retrieve",
                "search_shopping": "hybrid_retrieve",
                "search_knowledge_base": "hybrid_retrieve",
            }
            if should_prefer_fallback(user_id, "general", tool) and fallback_map.get(tool) in available:
                effective_tool = fallback_map[tool]
                learned_from = tool
            value = await execute_tool(effective_tool, args if effective_tool != "hybrid_retrieve" else {"query": goal, "include_web": True}, user_id=user_id)
            failed = isinstance(value, str) and value.startswith(("خطا در اجرای", "زمان اجرای", "ابزار ناشناخته"))
            record(user_id, "general", tool, not failed, "tool failure" if failed else "")
            if failed and repairs < MAX_REPAIRS:
                repairs += 1
                fallback = "get_user_city" if tool in {"get_weather", "get_air_quality"} and not args.get("city") else None
                if fallback and fallback in available:
                    city = await execute_tool(fallback, {}, user_id=user_id)
                    retry_args = dict(args)
                    if city and not str(city).startswith(("خطا", "ابزار ناشناخته")):
                        retry_args["city"] = str(city).strip()
                        value = await execute_tool(tool, retry_args, user_id=user_id)
                        results.append({"step": index, "tool": tool, "executed_tool": effective_tool, "learned_from": learned_from, "repaired": True, "result": str(value)[:3000]})
                        continue
            results.append({"step": index, "tool": tool, "executed_tool": effective_tool, "learned_from": learned_from, "repaired": repairs > 0 and failed, "result": str(value)[:3000]})
        except Exception as exc:
            logger.warning("agent step %s failed: %s", index, exc, exc_info=True)
            if repairs >= MAX_REPAIRS:
                return str({"ok": False, "failed_step": index, "steps": results})[:7000]
            repairs += 1
            results.append({"step": index, "tool": tool, "repaired": False, "error": str(exc)[:800]})

    return str({"ok": True, "goal": goal[:500], "steps": results, "repairs": repairs})[:7000]

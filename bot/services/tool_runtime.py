"""AI tool registry and execution runtime.

Built-in handlers remain in ai_tools.py; this module owns the generic runtime
so adding tools does not require growing the execution engine.
"""
from __future__ import annotations
import inspect
import json
import re
import asyncio
import os
import time
from typing import Any, Callable, Dict, List, Optional
from bot.logger import logger
from bot.utils.observability import record as record_metric

_REGISTRY: Dict[str, dict] = {}
_TOOL_INFLIGHT: Dict[str, asyncio.Task] = {}
_TOOL_INFLIGHT_LOCK = asyncio.Lock()
_TOOL_SEMAPHORE = asyncio.Semaphore(max(2, int(os.getenv("AI_TOOL_CONCURRENCY", "8"))))
_TOOL_CACHE: Dict[tuple, tuple[float, str]] = {}
_TOOL_CACHE_TTL = max(5, int(os.getenv("AI_TOOL_CACHE_TTL", "20")))
_TOOL_TIMEOUT = max(5.0, float(os.getenv("AI_TOOL_TIMEOUT", "25")))
_TOOL_CACHE_MAX = max(64, int(os.getenv("AI_TOOL_CACHE_MAX", "1024")))
_TOOL_CACHEABLE = {
    "get_weather", "get_weather_forecast", "get_air_quality",
    "get_market_prices", "get_top_crypto", "get_user_city",
}

_REGISTRY: Dict[str, dict] = {}
_TOOL_INFLIGHT: Dict[str, asyncio.Task] = {}
_TOOL_INFLIGHT_LOCK = asyncio.Lock()

_TOOL_SEMAPHORE = asyncio.Semaphore(max(2, int(os.getenv("AI_TOOL_CONCURRENCY", "8"))))
_TOOL_CACHE: Dict[tuple, tuple[float, str]] = {}
_TOOL_CACHE_TTL = max(5, int(os.getenv("AI_TOOL_CACHE_TTL", "20")))
_TOOL_TIMEOUT = max(5.0, float(os.getenv("AI_TOOL_TIMEOUT", "25")))
_TOOL_CACHEABLE = {
    "get_weather", "get_weather_forecast", "get_air_quality",
    "get_market_prices", "get_top_crypto", "get_user_city",
}


def register_tool(
    name: str,
    description: str,
    parameters: Optional[dict] = None,
    handler: Optional[Callable] = None,
    *,
    keywords: Optional[List[str]] = None,
) -> None:
    """ثبت یک ابزار برای AI. keywords برای تزریق خودکار وقتی مدل tool ندارد."""
    if not name or not handler:
        raise ValueError("name و handler الزامی‌اند")
    _REGISTRY[name] = {
        "name": name,
        "description": description,
        "parameters": parameters or {"type": "object", "properties": {}},
        "handler": handler,
        "keywords": keywords or [],
        "cacheable": False,
    }
    logger.debug("AI tool registered: %s", name)


def get_registered_tool_names() -> set[str]:
    """Return a snapshot of registered tool names for workflow validation."""
    return set(_REGISTRY)


def get_tool_definitions() -> List[dict]:
    """لیست tools به فرمت OpenAI/Groq."""
    out = []
    for t in _REGISTRY.values():
        out.append(
            {
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t["description"],
                    "parameters": t["parameters"],
                },
            }
        )
    return out


def parse_tool_arguments(raw: Any) -> dict:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            return json.loads(raw) if raw.strip() else {}
        except Exception:
            return {}
    return {}


async def execute_tool(name: str, arguments: dict, *, user_id: int = 0) -> str:
    entry = _REGISTRY.get(name)
    if not entry:
        return f"ابزار ناشناخته: {name}"
    handler = entry["handler"]
    args = dict(arguments or {})
    try:
        sig = inspect.signature(handler)
        if "user_id" in sig.parameters:
            args.setdefault("user_id", user_id)
        allowed = set(sig.parameters.keys())
        args = {k: v for k, v in args.items() if k in allowed}
    except Exception:
        pass

    # Cache only explicitly read-only tools; never cache reminders, writes or side effects.
    try:
        fingerprint = json.dumps([name, user_id, args], ensure_ascii=False, sort_keys=True, default=str)
    except Exception:
        fingerprint = f"{name}:{user_id}:{repr(args)}"
    if name in _TOOL_CACHEABLE:
        cached = _TOOL_CACHE.get((name, user_id, fingerprint))
        if cached and cached[0] > time.monotonic():
            return cached[1]
        _TOOL_CACHE.pop((name, user_id, fingerprint), None)

    async with _TOOL_INFLIGHT_LOCK:
        task = _TOOL_INFLIGHT.get(fingerprint)
        if task is None or task.done():
            async def _run():
                try:
                    async with _TOOL_SEMAPHORE:
                        _started = time.monotonic()
                        if inspect.iscoroutinefunction(handler):
                            result = await asyncio.wait_for(handler(**args), timeout=_TOOL_TIMEOUT)
                        else:
                            result = await asyncio.wait_for(asyncio.to_thread(handler, **args), timeout=_TOOL_TIMEOUT)
                    text = str(result)[:4500] if result is not None else "نتیجه‌ای برنگشت."
                    record_metric("ai_tool", name, ok=True, latency=time.monotonic() - _started)
                    if name in _TOOL_CACHEABLE:
                        # Keep the read-through cache bounded even on long-running bots.
                        now = time.monotonic()
                        _TOOL_CACHE[(name, user_id, fingerprint)] = (now + _TOOL_CACHE_TTL, text)
                        if len(_TOOL_CACHE) > 1024:
                            stale = [k for k, (expires, _) in _TOOL_CACHE.items() if expires <= now]
                            for k in stale[:512]:
                                _TOOL_CACHE.pop(k, None)
                            if len(_TOOL_CACHE) > _TOOL_CACHE_MAX:
                                overflow = len(_TOOL_CACHE) - _TOOL_CACHE_MAX
                                for k in list(_TOOL_CACHE)[:overflow]:
                                    _TOOL_CACHE.pop(k, None)
                    return text
                except asyncio.TimeoutError:
                    record_metric("ai_tool", name, ok=False, latency=time.monotonic() - _started)
                    logger.warning("tool %s timed out after %ss", name, _TOOL_TIMEOUT)
                    return f"زمان اجرای {name} تمام شد؛ دوباره تلاش کن."
                except Exception as e:
                    record_metric("ai_tool", name, ok=False, latency=time.monotonic() - _started)
                    logger.warning("tool %s failed: %s", name, e, exc_info=True)
                    return f"خطا در اجرای {name}: {e}"
            from bot.utils.task_manager import spawn
            task = spawn(_run(), name=f"ai-tool-{name}")
            _TOOL_INFLIGHT[fingerprint] = task
    try:
        return await task
    finally:
        if task.done():
            async with _TOOL_INFLIGHT_LOCK:
                if _TOOL_INFLIGHT.get(fingerprint) is task:
                    _TOOL_INFLIGHT.pop(fingerprint, None)


async def gather_context_for_prompt(user_id: int, prompt: str) -> str:
    """
    Compatibility fallback for providers that do not support function calling.

    IMPORTANT: never execute a tool that has required arguments with ``{}``.
    That old behaviour could silently call tools with invalid parameters and
    inject unrelated data into the prompt. Only zero-argument tools are safe
    to prefetch here. Providers with native function calling should use the
    registry directly instead.
    """
    text = (prompt or "").strip()
    if not text:
        return ""

    chunks: List[str] = []
    used = set()
    for name, entry in _REGISTRY.items():
        if name in used:
            continue
        kws = entry.get("keywords") or []
        if not kws:
            continue
        params = entry.get("parameters") or {}
        required = params.get("required") or []
        if required:
            continue
        for kw in kws:
            try:
                if re.search(kw, text, re.I):
                    result = await execute_tool(name, {}, user_id=user_id)
                    if result and not str(result).startswith("خطا") and not str(result).startswith("ابزار ناشناخته"):
                        chunks.append(f"[{name}]\n{result}")
                        used.add(name)
                    break
            except Exception as e:
                logger.warning("gather_context %s: %s", name, e)

    if not chunks:
        return ""
    return (
        "\n\n[دادهٔ زنده از قابلیت‌های ربات — فقط از این اطلاعات برای اعداد و وضعیت واقعی استفاده کن]\n"
        + "\n---\n".join(chunks[:6])
    )


def list_registered_tools() -> List[str]:
    return sorted(_REGISTRY.keys())


def clear_tool_cache() -> None:
    """Clear read-through tool cache without touching tool registry/state."""
    _TOOL_CACHE.clear()

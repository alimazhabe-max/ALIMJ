"""Bounded multi-step tool workflows for the AI agent.

A workflow is a small sequential plan. Each step calls one registered tool and
may reference previous results with ``$stepN`` or ``$stepN.field`` in arguments.
The engine is deliberately bounded to avoid runaway agent loops.
"""
from __future__ import annotations

import json
import os
import re
from typing import Any

from bot.logger import logger

MAX_STEPS = max(1, min(8, int(os.getenv("AI_WORKFLOW_MAX_STEPS", "4"))))
MAX_RESULT_CHARS = max(1000, min(12000, int(os.getenv("AI_WORKFLOW_MAX_RESULT_CHARS", "7000"))))


def _resolve(value: Any, results: list[Any]) -> Any:
    if isinstance(value, dict):
        return {k: _resolve(v, results) for k, v in value.items()}
    if isinstance(value, list):
        return [_resolve(v, results) for v in value]
    if not isinstance(value, str) or not value.startswith("$step"):
        return value
    m = re.fullmatch(r"\$step(\d+)(?:\.(.+))?", value)
    if not m:
        return value
    idx = int(m.group(1)) - 1
    if idx < 0 or idx >= len(results):
        raise ValueError(f"reference to unavailable step: {value}")
    result = results[idx]
    path = m.group(2)
    if not path:
        return result
    for part in path.split("."):
        if isinstance(result, dict) and part in result:
            result = result[part]
        else:
            raise ValueError(f"field not found in {value}")
    return result


async def run_workflow(steps: list[dict], *, user_id: int = 0) -> str:
    """Execute a bounded sequential workflow using the existing tool registry."""
    if not isinstance(steps, list) or not steps:
        return "workflow خالی است."
    if len(steps) > MAX_STEPS:
        return f"workflow بیش از حد طولانی است؛ حداکثر {MAX_STEPS} مرحله مجاز است."

    # Local import avoids circular import during tool registration.
    from bot.services.ai_tools import execute_tool, get_registered_tool_names

    results: list[Any] = []
    transcript: list[dict] = []
    for number, step in enumerate(steps, 1):
        if not isinstance(step, dict):
            return f"مرحله {number} معتبر نیست."
        name = str(step.get("tool") or "").strip()
        if not name or name not in get_registered_tool_names():
            return f"ابزار مرحله {number} معتبر نیست: {name or 'نامشخص'}"
        if name == "run_workflow":
            return "workflow تو در تو مجاز نیست."
        raw_args = step.get("arguments", {})
        if not isinstance(raw_args, dict):
            return f"arguments مرحله {number} باید object باشد."
        try:
            args = _resolve(raw_args, results)
            result = await execute_tool(name, args, user_id=user_id)
        except Exception as exc:
            logger.warning("workflow step %s (%s) failed: %s", number, name, exc, exc_info=True)
            return json.dumps({"ok": False, "failed_step": number, "tool": name, "error": str(exc)}, ensure_ascii=False)[:MAX_RESULT_CHARS]
        text = str(result)
        results.append(text)
        transcript.append({"step": number, "tool": name, "result": text[:2500]})
        if text.startswith("خطا در اجرای") or text.startswith("زمان اجرای") or text.startswith("ابزار ناشناخته"):
            return json.dumps({"ok": False, "failed_step": number, "steps": transcript}, ensure_ascii=False)[:MAX_RESULT_CHARS]

    return json.dumps({"ok": True, "steps": transcript, "final": results[-1] if results else ""}, ensure_ascii=False)[:MAX_RESULT_CHARS]

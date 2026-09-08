"""Small, privacy-conscious learning loop for agent/tool reliability.

Only aggregate success/failure counters and a short last error are retained;
conversation text is never stored here.
"""
from __future__ import annotations

from bot.database import get_agent_tool_reliability, record_agent_outcome

MIN_ATTEMPTS_FOR_FALLBACK = 3
LOW_RELIABILITY_THRESHOLD = 0.25


def record(user_id: int, agent: str, tool: str, success: bool, error: str = "") -> None:
    try:
        record_agent_outcome(user_id, agent, tool, success, error)
    except Exception:
        # Learning must never break the actual agent request.
        return


def reliability(user_id: int, agent: str, tool: str) -> tuple[float, int, int]:
    try:
        return get_agent_tool_reliability(user_id, agent, tool)
    except Exception:
        return 0.5, 0, 0


def should_prefer_fallback(user_id: int, agent: str, tool: str) -> bool:
    score, attempts, _failures = reliability(user_id, agent, tool)
    return attempts >= MIN_ATTEMPTS_FOR_FALLBACK and score < LOW_RELIABILITY_THRESHOLD

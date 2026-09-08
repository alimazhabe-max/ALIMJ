"""Lightweight in-process observability for AI, tools and HTTP traffic."""
from __future__ import annotations
import threading
import time
from collections import defaultdict, deque
from typing import Any

_LOCK = threading.Lock()
_COUNTERS: dict[str, int] = defaultdict(int)
_LATENCY: dict[str, deque[float]] = defaultdict(lambda: deque(maxlen=200))
_ERROR_EVENTS: deque[dict[str, Any]] = deque(maxlen=50)


def record(kind: str, name: str, *, ok: bool = True, latency: float | None = None, **labels: Any) -> None:
    key = ":".join([kind, name] + [f"{k}={labels[k]}" for k in sorted(labels)])
    with _LOCK:
        _COUNTERS[f"{key}:total"] += 1
        _COUNTERS[f"{key}:{'ok' if ok else 'fail'}"] += 1
        if latency is not None:
            _LATENCY[key].append(max(0.0, float(latency)))



def record_error(source: str, error: BaseException | str, *, user_id: int | None = None) -> None:
    """Keep a small, bounded in-process error trail without storing secrets."""
    text = str(error or "")
    # Avoid retaining potentially huge exception payloads or Telegram/API content.
    text = text.replace("\n", " ").strip()[:240]
    item = {
        "time": time.time(),
        "source": str(source)[:80],
        "type": type(error).__name__[:80] if isinstance(error, BaseException) else "Error",
        "message": text,
    }
    if user_id is not None:
        item["user_id"] = int(user_id)
    with _LOCK:
        _ERROR_EVENTS.append(item)


def recent_errors(limit: int = 10) -> list[dict[str, Any]]:
    """Return the newest bounded error events."""
    limit = max(1, min(int(limit), 50))
    with _LOCK:
        return list(reversed(list(_ERROR_EVENTS)[-limit:]))

def snapshot() -> dict[str, Any]:
    with _LOCK:
        counters = dict(_COUNTERS)
        latency = {}
        for key, values in _LATENCY.items():
            vals = list(values)
            if vals:
                latency[key] = {
                    "count": len(vals),
                    "avg_ms": round(sum(vals) * 1000 / len(vals), 1),
                    "p95_ms": round(sorted(vals)[max(0, int(len(vals) * .95) - 1)] * 1000, 1),
                }
    try:
        from bot.utils.task_manager import stats as task_stats
        tasks = task_stats()
    except Exception:
        tasks = {"tracked": 0, "active": 0}
    return {"counters": counters, "latency": latency, "tasks": tasks, "recent_errors": recent_errors(10), "generated_at": time.time()}


def reset() -> None:
    with _LOCK:
        _COUNTERS.clear()
        _LATENCY.clear()
        _ERROR_EVENTS.clear()

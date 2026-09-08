"""Lightweight in-process observability for AI, tools and HTTP traffic."""
from __future__ import annotations
import threading
import time
from collections import defaultdict, deque
from typing import Any

_LOCK = threading.Lock()
_COUNTERS: dict[str, int] = defaultdict(int)
_LATENCY: dict[str, deque[float]] = defaultdict(lambda: deque(maxlen=200))


def record(kind: str, name: str, *, ok: bool = True, latency: float | None = None, **labels: Any) -> None:
    key = ":".join([kind, name] + [f"{k}={labels[k]}" for k in sorted(labels)])
    with _LOCK:
        _COUNTERS[f"{key}:total"] += 1
        _COUNTERS[f"{key}:{'ok' if ok else 'fail'}"] += 1
        if latency is not None:
            _LATENCY[key].append(max(0.0, float(latency)))


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
    return {"counters": counters, "latency": latency, "tasks": tasks, "generated_at": time.time()}


def reset() -> None:
    with _LOCK:
        _COUNTERS.clear()
        _LATENCY.clear()

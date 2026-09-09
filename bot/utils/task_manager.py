"""Bounded background-task lifecycle management for the long-running bot."""
from __future__ import annotations
import asyncio
from collections.abc import Coroutine
from typing import Any
from bot.logger import logger

_TASKS: set[asyncio.Task[Any]] = set()


def spawn(coro: Coroutine[Any, Any, Any], *, name: str | None = None) -> asyncio.Task[Any]:
    """Create and track a background task so shutdown never leaves orphans."""
    task = asyncio.create_task(coro, name=name)
    _TASKS.add(task)
    task.add_done_callback(_discard)
    return task


def _discard(task: asyncio.Task[Any]) -> None:
    _TASKS.discard(task)
    if task.cancelled():
        return
    try:
        exc = task.exception()
    except asyncio.CancelledError:
        return
    if exc:
        logger.warning("Background task failed: %s", exc, exc_info=exc)


def stats() -> dict[str, int]:
    return {"tracked": len(_TASKS), "active": sum(not t.done() for t in _TASKS)}


def tracked_task_count() -> int:
    """Return the number of currently tracked tasks."""
    return len(_TASKS)


async def shutdown(timeout: float = 5.0) -> None:
    """Cancel tracked background tasks and wait a bounded amount of time."""
    tasks = [t for t in _TASKS if not t.done()]
    if not tasks:
        return
    for task in tasks:
        task.cancel()
    try:
        await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), timeout=max(0.5, timeout))
    except asyncio.TimeoutError:
        logger.warning("Background task shutdown timed out; %d task(s) remain", len(tasks))
    finally:
        _TASKS.difference_update(tasks)

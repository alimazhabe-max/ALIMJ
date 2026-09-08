"""Shared async HTTP resilience: pooled connections, retries and lightweight TTL cache."""
from __future__ import annotations

import asyncio
import time
from contextlib import asynccontextmanager
from typing import Any, Optional

import httpx

from bot.logger import logger
from bot.utils.http_client import get_async_client, request_with_retry

_MAX_CONNECTIONS = 60
_MAX_KEEPALIVE = 30
_DEFAULT_TIMEOUT = float(__import__('os').getenv('HTTP_DEFAULT_TIMEOUT', '15'))
_RETRIES = max(0, int(__import__('os').getenv('HTTP_RETRIES', '2')))
_BACKOFF = float(__import__('os').getenv('HTTP_RETRY_BACKOFF', '0.35'))



class _PooledProxy:
    def __init__(self, *, timeout=None, headers=None, follow_redirects=True):
        self.timeout = timeout
        self.headers = headers or {}
        self.follow_redirects = follow_redirects

    def _kwargs(self, kwargs):
        kwargs.setdefault('timeout', self.timeout)
        kwargs.setdefault('follow_redirects', self.follow_redirects)
        if self.headers:
            merged = dict(self.headers)
            merged.update(kwargs.get('headers') or {})
            kwargs['headers'] = merged
        return kwargs

    async def get(self, url: str, **kwargs):
        return await request_with_retry('GET', url, **self._kwargs(kwargs))

    async def post(self, url: str, **kwargs):
        return await request_with_retry('POST', url, **self._kwargs(kwargs))


@asynccontextmanager
async def pooled_client(*, timeout=None, headers=None, follow_redirects=True):
    """Shared pooled client facade used by market/weather modules."""
    yield _PooledProxy(timeout=timeout, headers=headers, follow_redirects=follow_redirects)


_RETRYABLE_STATUS = {408, 425, 429, 500, 502, 503, 504}




_CACHE: dict[str, tuple[float, Any]] = {}
_CACHE_LOCK = asyncio.Lock()


async def cache_get(key: str) -> Any:
    item = _CACHE.get(key)
    if not item:
        return None
    expires, value = item
    if expires <= time.monotonic():
        _CACHE.pop(key, None)
        return None
    return value


async def cache_set(key: str, value: Any, ttl: float) -> None:
    if ttl <= 0:
        return
    async with _CACHE_LOCK:
        _CACHE[key] = (time.monotonic() + ttl, value)
        if len(_CACHE) > 2048:
            now = time.monotonic()
            for k, (expires, _) in list(_CACHE.items())[:512]:
                if expires <= now:
                    _CACHE.pop(k, None)


async def close_http_pool() -> None:
    from bot.utils.http_client import close_async_client
    await close_async_client()

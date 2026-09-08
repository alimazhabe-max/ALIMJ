"""Shared HTTP clients with connection pooling and conservative retry policy."""
from __future__ import annotations
import asyncio
import time
import hashlib
from contextlib import asynccontextmanager
from typing import Any
from bot.utils.observability import record as record_metric
import httpx

_DEFAULT_TIMEOUT = float(__import__('os').getenv('HTTP_TIMEOUT', '15'))
_RETRIES = max(0, int(__import__('os').getenv('HTTP_RETRIES', '2')))
_RETRY_STATUSES = {408, 425, 429, 500, 502, 503, 504}

_async_client: httpx.AsyncClient | None = None
_async_lock = asyncio.Lock()

_GET_CACHE: dict[str, tuple[float, httpx.Response]] = {}
_GET_CACHE_MAX = max(64, int(__import__('os').getenv('HTTP_GET_CACHE_MAX', '1024')))
_GET_CACHE_TTL = max(0, float(__import__('os').getenv('HTTP_GET_CACHE_TTL', '12')))

def _cache_key(url: str, kwargs: dict[str, Any]) -> str:
    params = kwargs.get('params')
    headers = kwargs.get('headers') or {}
    try:
        raw = repr((url, sorted((params or {}).items()), sorted((headers or {}).items())))
    except Exception:
        raw = repr((url, params, headers))
    return hashlib.sha256(raw.encode('utf-8', 'ignore')).hexdigest()

async def get_async_client() -> httpx.AsyncClient:
    global _async_client
    if _async_client is None or _async_client.is_closed:
        async with _async_lock:
            if _async_client is None or _async_client.is_closed:
                _async_client = httpx.AsyncClient(
                    timeout=httpx.Timeout(_DEFAULT_TIMEOUT, connect=5.0),
                    limits=httpx.Limits(max_keepalive_connections=30, max_connections=60),
                    follow_redirects=True,
                    http2=False,
                )
    return _async_client

@asynccontextmanager
async def pooled_async_client():
    """Yield the shared client without closing it at the end of a request."""
    yield await get_async_client()

async def request_with_retry(method: str, url: str, *, retries: int | None = None, **kwargs: Any) -> httpx.Response:
    """HTTP request with retry/backoff and a short GET cache to reduce API pressure."""
    method = method.upper()
    cache_key = _cache_key(url, kwargs) if method == 'GET' and _GET_CACHE_TTL > 0 else None
    if cache_key:
        cached = _GET_CACHE.get(cache_key)
        if cached and cached[0] > time.monotonic():
            return cached[1]
        _GET_CACHE.pop(cache_key, None)

    client = await get_async_client()
    attempts = _RETRIES if retries is None else max(0, retries)
    last: Exception | None = None
    for attempt in range(attempts + 1):
        try:
            started = time.monotonic()
            response = await client.request(method, url, **kwargs)
            record_metric("http", method, ok=response.status_code < 400, latency=time.monotonic() - started, status=response.status_code)
            if response.status_code not in _RETRY_STATUSES or attempt >= attempts:
                if cache_key and response.status_code == 200:
                    _GET_CACHE[cache_key] = (time.monotonic() + _GET_CACHE_TTL, response)
                    if len(_GET_CACHE) > _GET_CACHE_MAX:
                        now = time.monotonic()
                        for k, (expires, _) in list(_GET_CACHE.items()):
                            if expires <= now:
                                _GET_CACHE.pop(k, None)
                        if len(_GET_CACHE) > _GET_CACHE_MAX:
                            # Dict insertion order gives a cheap FIFO-style bound.
                            overflow = len(_GET_CACHE) - _GET_CACHE_MAX
                            for k in list(_GET_CACHE)[:overflow]:
                                _GET_CACHE.pop(k, None)
                return response
            retry_after = response.headers.get('retry-after')
            try:
                delay = min(4.0, max(0.15, float(retry_after))) if retry_after else 0.35 * (2 ** attempt)
            except ValueError:
                delay = 0.35 * (2 ** attempt)
            await asyncio.sleep(delay)
        except (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError) as exc:
            last = exc
            if attempt >= attempts:
                raise
            await asyncio.sleep(min(4.0, 0.35 * (2 ** attempt)))
    if last:
        raise last
    raise RuntimeError('HTTP request failed')

async def close_async_client() -> None:
    global _async_client
    if _async_client is not None and not _async_client.is_closed:
        await _async_client.aclose()
    _async_client = None


def clear_http_cache() -> None:
    """Drop in-memory GET responses during lifecycle shutdown/tests."""
    _GET_CACHE.clear()

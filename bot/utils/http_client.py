"""Shared HTTP clients with connection pooling and conservative retry policy."""
from __future__ import annotations
import asyncio
import time
import hashlib
import os
from dataclasses import dataclass
from contextlib import asynccontextmanager
from typing import Any
from urllib.parse import urlparse
from bot.utils.exceptions import UpstreamTimeoutError
from bot.utils.observability import record as record_metric
import httpx


@dataclass(frozen=True)
class HTTPSettings:
    timeout: float = 15.0
    retries: int = 2
    cache_ttl: float = 12.0
    cache_max: int = 1024
    rate_limit_max_delay: float = 10.0


def _env_float(name: str, default: float, minimum: float = 0.0) -> float:
    try:
        return max(minimum, float(os.getenv(name, str(default))))
    except (TypeError, ValueError):
        return default


def _env_int(name: str, default: int, minimum: int = 0) -> int:
    try:
        return max(minimum, int(os.getenv(name, str(default))))
    except (TypeError, ValueError):
        return default


_SETTINGS = HTTPSettings(
    timeout=_env_float('HTTP_TIMEOUT', 15.0, 0.1),
    retries=_env_int('HTTP_RETRIES', 2),
    cache_ttl=_env_float('HTTP_GET_CACHE_TTL', 12.0),
    cache_max=max(64, _env_int('HTTP_GET_CACHE_MAX', 1024, 64)),
    rate_limit_max_delay=max(1.0, _env_float('HTTP_429_MAX_DELAY', 10.0, 1.0)),
)

_DEFAULT_TIMEOUT = _SETTINGS.timeout
_RETRIES = _SETTINGS.retries
_RETRY_STATUSES = {408, 425, 429, 500, 502, 503, 504}

_async_client: httpx.AsyncClient | None = None
_async_lock = asyncio.Lock()

_GET_CACHE: dict[str, tuple[float, httpx.Response]] = {}
_GET_CACHE_MAX = _SETTINGS.cache_max
_GET_CACHE_TTL = _SETTINGS.cache_ttl
_RATE_LIMIT_MAX_DELAY = _SETTINGS.rate_limit_max_delay
_RATE_LIMIT_COOLDOWN: dict[str, float] = {}
_RATE_LIMIT_LOCK = asyncio.Lock()

def safe_json(response: Any, default: Any = None) -> Any:
    """Return decoded JSON without letting empty/non-JSON upstream bodies crash callers."""
    if response is None:
        return default
    try:
        return response.json()
    except (ValueError, TypeError, UnicodeDecodeError):
        return default


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

async def _wait_for_rate_limit(host: str) -> None:
    """Avoid sending another request while a host is in a known 429 cooldown."""
    async with _RATE_LIMIT_LOCK:
        until = _RATE_LIMIT_COOLDOWN.get(host, 0.0)
    delay = until - time.monotonic()
    if delay > 0:
        await asyncio.sleep(min(_RATE_LIMIT_MAX_DELAY, delay))


def _set_rate_limit(host: str, delay: float) -> None:
    if delay <= 0:
        return
    _RATE_LIMIT_COOLDOWN[host] = max(_RATE_LIMIT_COOLDOWN.get(host, 0.0), time.monotonic() + min(_RATE_LIMIT_MAX_DELAY, delay))
    if len(_RATE_LIMIT_COOLDOWN) > 128:
        now = time.monotonic()
        for key, until in list(_RATE_LIMIT_COOLDOWN.items()):
            if until <= now:
                _RATE_LIMIT_COOLDOWN.pop(key, None)


async def request_with_retry(method: str, url: str, *, retries: int | None = None, **kwargs: Any) -> httpx.Response:
    """HTTP request with retry/backoff, 429 host cooldown and a short GET cache."""
    method = method.upper()
    host = urlparse(url).netloc.lower()
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
        await _wait_for_rate_limit(host)
        try:
            started = time.monotonic()
            response = await client.request(method, url, **kwargs)
            elapsed = time.monotonic() - started
            # Host is safe, bounded diagnostic metadata; query strings/keys are never recorded.
            safe_host = host[:80] or "unknown"
            record_metric("http", method, ok=response.status_code < 400, latency=elapsed, status=response.status_code, host=safe_host)
            if response.status_code in (401, 403, 451):
                # These responses are not made better by retries. Preserve the response
                # for callers so existing fallback logic remains in control.
                return response
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
                delay = min(_RATE_LIMIT_MAX_DELAY, max(0.25, float(retry_after))) if retry_after else min(_RATE_LIMIT_MAX_DELAY, 0.8 * (2 ** attempt))
            except (TypeError, ValueError):
                delay = min(_RATE_LIMIT_MAX_DELAY, 0.8 * (2 ** attempt))
            if response.status_code == 429:
                _set_rate_limit(host, delay)
            await asyncio.sleep(delay)
        except httpx.TimeoutException as exc:
            last = UpstreamTimeoutError(str(exc) or "HTTP request timed out")
            if attempt >= attempts:
                raise last from exc
            await asyncio.sleep(min(4.0, 0.35 * (2 ** attempt)))
        except (httpx.NetworkError, httpx.RemoteProtocolError) as exc:
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
    _RATE_LIMIT_COOLDOWN.clear()

"""Shared resilient HTTP primitives for ALIMJ.
Keeps provider retries bounded, reuses connections, and supports stale cache values.
"""
from __future__ import annotations
import asyncio, random, time
from typing import Any, Optional
import httpx
from bot.logger import logger

_CLIENTS: dict[str, httpx.AsyncClient] = {}

async def get_client(name: str = "default", *, timeout: float = 12.0) -> httpx.AsyncClient:
    client = _CLIENTS.get(name)
    if client is None or client.is_closed:
        _CLIENTS[name] = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout, connect=min(5.0, timeout)),
            limits=httpx.Limits(max_keepalive_connections=20, max_connections=50),
            follow_redirects=True,
            headers={"User-Agent": "ALIMJBot/2.0"},
        )
    return _CLIENTS[name]

async def request_json(method: str, url: str, *, client_name: str = "default",
                       timeout: float = 12.0, retries: int = 2, **kwargs) -> tuple[int, Any]:
    client = await get_client(client_name, timeout=timeout)
    last_exc: Optional[Exception] = None
    for attempt in range(retries + 1):
        try:
            response = await client.request(method, url, timeout=timeout, **kwargs)
            if response.status_code not in (408, 425) and response.status_code < 500:
                try: data = response.json()
                except Exception: data = {"raw": response.text[:1500]}
                return response.status_code, data
            if attempt < retries:
                await asyncio.sleep(min(2.5, 0.25 * (2 ** attempt) + random.random() * 0.15))
                continue
            try: data = response.json()
            except Exception: data = {"raw": response.text[:1500]}
            return response.status_code, data
        except (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError) as exc:
            last_exc = exc
            if attempt < retries:
                await asyncio.sleep(min(2.5, 0.25 * (2 ** attempt) + random.random() * 0.15))
                continue
    raise last_exc or RuntimeError("HTTP request failed")

async def close_all() -> None:
    clients = list(_CLIENTS.values())
    _CLIENTS.clear()
    for client in clients:
        try:
            await client.aclose()
        except Exception as exc:
            logger.debug("HTTP client close: %s", exc)

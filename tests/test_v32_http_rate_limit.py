import asyncio
import importlib.util
import pathlib
import sys
import types


def _load_module():
    root = pathlib.Path(__file__).resolve().parents[1]
    name = "bot.utils.http_client"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, root / "bot/utils/http_client.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_rate_limit_cooldown_is_bounded_and_host_scoped():
    mod = _load_module()
    mod._RATE_LIMIT_COOLDOWN.clear()
    mod._set_rate_limit("api.example", 999)
    assert "api.example" in mod._RATE_LIMIT_COOLDOWN
    remaining = mod._RATE_LIMIT_COOLDOWN["api.example"] - mod.time.monotonic()
    assert 0 < remaining <= mod._RATE_LIMIT_MAX_DELAY
    mod._set_rate_limit("other.example", 1)
    assert len(mod._RATE_LIMIT_COOLDOWN) == 2
    mod._RATE_LIMIT_COOLDOWN.clear()


def test_retry_after_429_uses_cooldown(monkeypatch):
    mod = _load_module()
    class Resp:
        status_code = 429
        headers = {"retry-after": "2"}
    mod._RATE_LIMIT_COOLDOWN.clear()
    mod._set_rate_limit("api.example", 2)
    remaining = mod._RATE_LIMIT_COOLDOWN["api.example"] - mod.time.monotonic()
    assert remaining <= 2.05
    mod._RATE_LIMIT_COOLDOWN.clear()

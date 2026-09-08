import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_workflow_reference_and_bounds(monkeypatch):
    from bot.services import ai_tools
    from bot.services.workflow_engine import run_workflow

    calls = []

    async def first(value="ok", user_id=0):
        calls.append(("first", value, user_id))
        return "42"

    async def second(value="", user_id=0):
        calls.append(("second", value, user_id))
        return {"seen": value}

    old = dict(ai_tools._REGISTRY)
    try:
        ai_tools._REGISTRY.clear()
        ai_tools.register_tool("first", "test", {"type":"object","properties":{"value":{"type":"string"}}}, first)
        ai_tools.register_tool("second", "test", {"type":"object","properties":{"value":{"type":"string"}}}, second)
        out = asyncio.run(run_workflow([
            {"tool":"first", "arguments":{"value":"x"}},
            {"tool":"second", "arguments":{"value":"$step1"}},
        ], user_id=7))
        data = json.loads(out)
        assert data["ok"] is True
        assert calls[-1] == ("second", "42", 7)
    finally:
        ai_tools._REGISTRY.clear()
        ai_tools._REGISTRY.update(old)


def test_workflow_rejects_unknown_and_nested():
    from bot.services.workflow_engine import run_workflow
    assert "معتبر نیست" in asyncio.run(run_workflow([{"tool":"does_not_exist"}]))
    assert "تو در تو" in asyncio.run(run_workflow([{"tool":"run_workflow"}]))

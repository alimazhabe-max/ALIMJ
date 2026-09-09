from pathlib import Path
import hashlib
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bot.utils.http_client import safe_json

JOKES = ROOT / "bot/features/fun/jokes_data.json"
JOKES_SHA = "dc573e2a954af897350caa4183a98f33d5ed71327fed02c7ebe053d893e3a508"


class EmptyResponse:
    def json(self):
        raise ValueError("Expecting value: line 1 column 1 (char 0)")


def test_safe_json_handles_empty_non_json_response():
    assert safe_json(EmptyResponse()) is None
    assert safe_json(EmptyResponse(), {}) == {}


def test_market_modules_use_safe_json_for_response_decoding():
    market = ROOT / "bot/features/market"
    for name in ("finance.py", "finance_core.py", "finance_crypto.py", "finance_ta.py"):
        text = (market / name).read_text(encoding="utf-8")
        assert ".json()" not in text
        assert "safe_json" in text


def test_jokes_are_unchanged():
    assert hashlib.sha256(JOKES.read_bytes()).hexdigest() == JOKES_SHA

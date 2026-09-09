from pathlib import Path
import hashlib
import sys
import ast

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

JOKES = ROOT / "bot/features/fun/jokes_data.json"
JOKES_SHA = "dc573e2a954af897350caa4183a98f33d5ed71327fed02c7ebe053d893e3a508"


def test_domain_handler_modules_exist_and_parse():
    names = ["date_handlers.py", "market_handlers.py", "tools_handlers.py", "profile_handlers.py", "font_handlers.py"]
    for name in names:
        path = ROOT / "bot/handlers" / name
        assert path.exists(), name
        ast.parse(path.read_text(encoding="utf-8"))


def test_legacy_feature_facade_exports_all_handlers():
    text = (ROOT / "bot/handlers/feature_handlers.py").read_text(encoding="utf-8")
    expected = {
        "_h_date_convert", "_h_age_calc", "_h_birthday", "_h_zodiac", "_h_lunar",
        "_h_date_diff", "_h_age_diff", "_h_event_search", "_h_countdown", "_h_calc",
        "_h_profit", "_h_currency", "_h_crypto_full", "_h_crypto_pos", "_h_crypto_chart",
        "_h_crypto_analyze", "_h_distance", "_h_birth_save", "_h_count_text",
        "_h_font_text", "_h_font_all",
    }
    for name in expected:
        assert name in text
    assert "__all__" in text


def test_message_router_still_imports_facade():
    text = (ROOT / "bot/handlers/messages.py").read_text(encoding="utf-8")
    assert "from bot.handlers.feature_handlers import" in text


def test_jokes_immutable():
    assert hashlib.sha256(JOKES.read_bytes()).hexdigest() == JOKES_SHA

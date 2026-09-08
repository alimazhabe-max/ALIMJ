import ast
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MESSAGES = ROOT / 'bot/handlers/messages.py'
FEATURE = ROOT / 'bot/handlers/feature_handlers.py'
JOKES = ROOT / 'bot/features/fun/jokes_data.json'

EXPECTED = {
    '_h_date_convert', '_h_age_calc', '_h_birthday', '_h_zodiac', '_h_lunar',
    '_h_date_diff', '_h_age_diff', '_h_event_search', '_h_countdown', '_h_calc',
    '_h_profit', '_h_currency', '_h_crypto_full', '_h_crypto_pos',
    '_h_crypto_chart', '_h_crypto_analyze', '_h_distance', '_h_birth_save',
    '_h_count_text', '_h_font_text', '_h_font_all',
}


def defs(path):
    tree = ast.parse(path.read_text(encoding='utf-8'))
    return {n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}


def test_feature_handlers_contain_extracted_handlers():
    assert EXPECTED <= defs(FEATURE)
    assert not (EXPECTED & defs(MESSAGES))


def test_messages_keeps_compatibility_imports_and_router_bindings():
    text = MESSAGES.read_text(encoding='utf-8')
    assert 'from bot.handlers.feature_handlers import (' in text
    for name in EXPECTED:
        assert name in text


def test_messages_was_reduced_and_module_is_reasonably_sized():
    assert len(MESSAGES.read_text(encoding='utf-8').splitlines()) < 1100
    assert len(FEATURE.read_text(encoding='utf-8').splitlines()) < 350


def test_jokes_are_immutable():
    assert hashlib.sha256(JOKES.read_bytes()).hexdigest() == 'dc573e2a954af897350caa4183a98f33d5ed71327fed02c7ebe053d893e3a508'

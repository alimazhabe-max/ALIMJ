import ast
import asyncio
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JOKES = ROOT / 'bot/features/fun/jokes_data.json'
EXPECTED_JOKES = 'dc573e2a954af897350caa4183a98f33d5ed71327fed02c7ebe053d893e3a508'


def test_retrieval_module_ast_and_bounds():
    tree = ast.parse((ROOT/'bot/services/retrieval.py').read_text(encoding='utf-8'))
    assert any(isinstance(n, ast.AsyncFunctionDef) and n.name == 'hybrid_search' for n in tree.body)
    assert '_MAX_CONTEXT' in (ROOT/'bot/services/retrieval.py').read_text(encoding='utf-8')


def test_local_retrieval_no_network_by_default(monkeypatch):
    from bot.services import retrieval
    monkeypatch.setattr(retrieval, 'retrieve_local', lambda uid, q: {'memory': [('city','Tehran')], 'knowledge': []})
    async def fail_web(*a, **k):
        raise AssertionError('web must not be called')
    import bot.services.ai_extras as extras
    monkeypatch.setattr(extras, 'web_search', fail_web)
    out = asyncio.run(retrieval.hybrid_search(123, 'شهر من'))
    assert 'Tehran' in out


def test_hybrid_web_opt_in(monkeypatch):
    from bot.services import retrieval
    monkeypatch.setattr(retrieval, 'retrieve_local', lambda uid, q: {'memory': [], 'knowledge': []})
    async def fake_web(*a, **k):
        return 'WEB_RESULT'
    import bot.services.ai_extras as extras
    monkeypatch.setattr(extras, 'web_search', fake_web)
    out = asyncio.run(retrieval.hybrid_search(123, 'latest news', include_web=True))
    assert 'WEB_RESULT' in out


def test_hybrid_tool_registered():
    import bot.services.ai_tools as tools
    assert 'hybrid_retrieve' in tools.get_registered_tool_names()


def test_jokes_unchanged():
    assert hashlib.sha256(JOKES.read_bytes()).hexdigest() == EXPECTED_JOKES

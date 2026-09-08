from pathlib import Path
import ast, hashlib

ROOT = Path(__file__).resolve().parents[1]


def test_v24_modules_exist_and_helpers_facade_exports():
    assert (ROOT / 'bot/utils/keyboard_factory.py').exists()
    assert (ROOT / 'bot/utils/city_data.py').exists()
    src = (ROOT / 'bot/utils/helpers.py').read_text(encoding='utf-8')
    assert 'from bot.utils.keyboard_factory import (' in src
    assert 'from bot.utils.city_data import' in src
    # The large keyboard implementations should no longer live in helpers.py.
    assert 'def get_main_keyboard' not in src


def test_ast_all_python():
    for path in (ROOT / 'bot').rglob('*.py'):
        ast.parse(path.read_text(encoding='utf-8'))


def test_jokes_immutable():
    p = ROOT / 'bot/features/fun/jokes_data.json'
    assert hashlib.sha256(p.read_bytes()).hexdigest() == 'dc573e2a954af897350caa4183a98f33d5ed71327fed02c7ebe053d893e3a508'


def test_release():
    ns = {}
    exec((ROOT / 'bot/release.py').read_text(encoding='utf-8'), ns)
    assert ns['VERSION'] == '31.0.0'

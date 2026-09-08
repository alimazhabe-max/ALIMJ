import ast
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_main_imports_all_registered_commands():
    tree = ast.parse((ROOT / 'bot/main.py').read_text(encoding='utf-8'))
    imports = set()
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module == 'bot.handlers.commands':
            imports.update(alias.name for alias in node.names)
    for name in ('memory_command', 'automation_command', 'plugins_command'):
        assert name in imports


def test_database_core_imports_datetime_for_backup():
    source = (ROOT / 'bot/database_core.py').read_text(encoding='utf-8')
    assert 'from datetime import datetime' in source
    assert 'datetime.now().strftime' in source


def test_refresh_main_does_not_shadow_get_user_city():
    tree = ast.parse((ROOT / 'bot/handlers/callbacks.py').read_text(encoding='utf-8'))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == 'button_handler':
            for child in ast.walk(node):
                if isinstance(child, ast.ImportFrom) and child.module == 'bot.database':
                    assert all(alias.name != 'get_user_city' for alias in child.names)
            break
    else:
        raise AssertionError('button_handler not found')


def test_jokes_immutable():
    path = ROOT / 'bot/features/fun/jokes_data.json'
    assert hashlib.sha256(path.read_bytes()).hexdigest() == 'dc573e2a954af897350caa4183a98f33d5ed71327fed02c7ebe053d893e3a508'

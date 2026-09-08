import ast
import hashlib
from pathlib import Path


def test_database_core_isolated_and_facade_exports():
    import bot.database as db
    import bot.database_core as core
    assert callable(db.get_db_connection)
    assert callable(db.run_db_transaction)
    assert core.get_db_connection is not None
    assert db.DB_PATH


def test_tool_runtime_facade_and_registry():
    import bot.services.ai_tools as tools
    import bot.services.tool_runtime as runtime
    assert tools.register_tool is runtime.register_tool
    assert tools.execute_tool is runtime.execute_tool
    assert len(tools.get_registered_tool_names()) >= 4


def test_no_syntax_errors_in_bot():
    for path in Path("bot").rglob("*.py"):
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def test_jokes_immutable():
    path = Path("bot/features/fun/jokes_data.json")
    assert hashlib.sha256(path.read_bytes()).hexdigest() == "dc573e2a954af897350caa4183a98f33d5ed71327fed02c7ebe053d893e3a508"

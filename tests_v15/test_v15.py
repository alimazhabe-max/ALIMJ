import hashlib
import os
import sqlite3
import tempfile
from pathlib import Path

JOKES = Path(__file__).resolve().parents[1] / "bot" / "features" / "fun" / "jokes_data.json"
EXPECTED_JOKES_SHA = "dc573e2a954af897350caa4183a98f33d5ed71327fed02c7ebe053d893e3a508"


def test_jokes_immutable():
    assert hashlib.sha256(JOKES.read_bytes()).hexdigest() == EXPECTED_JOKES_SHA


def test_automation_schema_and_claim():
    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "test.db"
        os.environ["DB_PATH"] = str(db)
        os.environ["BOT_TOKEN"] = "test-token"
        # Import after DB_PATH override.
        import importlib
        import bot.config as cfg
        importlib.reload(cfg)
        import bot.database as database
        importlib.reload(database)
        database.init_db()
        database.set_daily_digest(42, True)
        assert database.get_automation_preferences(42)["daily_digest"] is True
        users = database.get_users_for_daily_digest("2026-09-08")
        assert [x[0] for x in users] == [42]
        assert database.mark_daily_digest_sent(42, "2026-09-08") is True
        assert database.mark_daily_digest_sent(42, "2026-09-08") is False


def test_digest_builder_is_conservative():
    # Structural test without importing Telegram.
    source = (Path(__file__).resolve().parents[1] / "bot" / "automation.py").read_text()
    assert "at most one digest" in source
    assert "get_upcoming_user_reminders" in source
    assert "get_top_user_features" in source

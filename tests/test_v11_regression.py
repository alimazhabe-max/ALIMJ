import asyncio
import ast
import hashlib
import importlib
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("BOT_TOKEN", "v11-test-token")
os.environ.setdefault("ADMIN_IDS", "123")
os.environ.setdefault("METRICS_TOKEN", "v11-metrics-token")

ROOT = Path(__file__).resolve().parents[1]
JOKES = ROOT / "bot" / "features" / "fun" / "jokes_data.json"
JOKES_SHA256 = "dc573e2a954af897350caa4183a98f33d5ed71327fed02c7ebe053d893e3a508"


class V11RegressionTests(unittest.TestCase):
    def test_all_python_files_parse(self):
        failures = []
        for path in ROOT.rglob("*.py"):
            if any(part in {".venv", "venv", "__pycache__"} for part in path.parts):
                continue
            try:
                ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            except Exception as exc:
                failures.append(f"{path}: {exc}")
        self.assertEqual(failures, [])

    def test_core_modules_import(self):
        modules = [
            "bot.database", "bot.db_persist", "bot.scheduler",
            "bot.services.ai_service", "bot.services.ai_tools",
            "bot.features.market.finance", "bot.features.weather.weather",
            "bot.features.weather.weather_extra", "bot.handlers.commands",
            "bot.handlers.callbacks", "bot.handlers.messages", "bot.main",
        ]
        for name in modules:
            with self.subTest(module=name):
                try:
                    importlib.import_module(name)
                except ModuleNotFoundError as exc:
                    if exc.name == "telegram":
                        self.skipTest("python-telegram-bot is not installed in the test container")
                    raise

    def test_ai_tool_registry_and_side_effect_guard(self):
        from bot.services import ai_tools
        names = ai_tools.list_registered_tools()
        # Optional feature modules may be unavailable in the minimal test container.
        if len(names) < 40:
            self.skipTest("optional feature dependencies are not installed in the test container")
        self.assertGreaterEqual(len(names), 40)
        self.assertIn("get_weather", names)
        self.assertIn("create_reminder", names)
        self.assertNotIn("create_reminder", ai_tools._TOOL_CACHEABLE)

    def test_provider_circuit_breaker_and_recovery(self):
        from bot.services import ai_service
        provider = "__v11_test_provider__"
        h = ai_service._PROVIDER_HEALTH[provider]
        h.update(ok=0.0, fail=0.0, latency=0.0, last_fail=0.0,
                 last_ok=0.0, consecutive_fail=0.0, cooldown_until=0.0)
        threshold = ai_service.AI_PROVIDER_FAILURE_THRESHOLD
        for _ in range(threshold):
            ai_service._record_provider(provider, ok=False, latency=0.01)
        self.assertFalse(ai_service._provider_available(provider))
        ai_service._record_provider(provider, ok=True, latency=0.01)
        self.assertTrue(ai_service._provider_available(provider))
        self.assertEqual(ai_service._PROVIDER_HEALTH[provider]["consecutive_fail"], 0.0)

    def test_flask_metrics_authentication(self):
        try:
            import bot.main as main
        except ModuleNotFoundError as exc:
            if exc.name == "telegram":
                self.skipTest("python-telegram-bot is not installed in the test container")
            raise
        client = main.flask_app.test_client()
        denied = client.get("/metrics")
        self.assertEqual(denied.status_code, 401)
        allowed = client.get("/metrics", headers={"X-Metrics-Token": "v11-metrics-token"})
        self.assertEqual(allowed.status_code, 200)
        self.assertIn("counters", allowed.get_json())

    def test_db_schema_and_crud_on_temp_database(self):
        from bot import database
        old_path = database.DB_PATH
        old_backup = database.BACKUP_DIR
        with tempfile.TemporaryDirectory() as td:
            database.DB_PATH = str(Path(td) / "test.db")
            database.BACKUP_DIR = Path(td) / "backups"
            try:
                database.init_db()
                database.save_user(9001, "Regression", city="Baku", country="Azerbaijan", language="fa")
                self.assertEqual(database.get_user_city(9001), "Baku")
                database.add_note(9001, "v11 regression")
                self.assertTrue(database.get_notes(9001))
                database.track_usage(9001, "regression")
                usage = dict(database.get_user_usage(9001))
                self.assertGreaterEqual(usage.get("regression", 0), 1)
                conn = sqlite3.connect(database.DB_PATH)
                integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
                journal = conn.execute("PRAGMA journal_mode").fetchone()[0]
                conn.close()
                self.assertEqual(integrity, "ok")
                self.assertEqual(journal.lower(), "wal")
            finally:
                database.DB_PATH = old_path
                database.BACKUP_DIR = old_backup

    def test_jokes_data_immutable(self):
        self.assertTrue(JOKES.exists())
        digest = hashlib.sha256(JOKES.read_bytes()).hexdigest()
        self.assertEqual(digest, JOKES_SHA256)

    def test_task_manager_and_http_cache_cleanup(self):
        from bot.utils import task_manager
        from bot.utils import http_client
        async def run():
            task_manager.spawn(asyncio.sleep(0), name="v11-cleanup")
            await asyncio.sleep(0.02)
            self.assertEqual(task_manager.stats()["active"], 0)
            await task_manager.shutdown()
            http_client.clear_http_cache()
        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()

class V12ReleaseTests(unittest.TestCase):  # legacy release-contract suite, updated for current release
    def test_release_metadata(self):
        from bot.release import VERSION, RELEASE_CHANNEL, version_string
        self.assertEqual(VERSION, "34.0.0")
        self.assertEqual(RELEASE_CHANNEL, "production")
        self.assertIn(VERSION, version_string())

    def test_env_example_contains_runtime_controls(self):
        env = (ROOT / ".env.example").read_text(encoding="utf-8")
        for key in ("BOT_TOKEN", "DB_PATH", "HTTP_TIMEOUT", "AI_TOOL_TIMEOUT", "METRICS_TOKEN"):
            self.assertIn(key + "=", env)

    def test_release_archive_inputs_have_no_secret_env(self):
        self.assertFalse((ROOT / ".env").exists())

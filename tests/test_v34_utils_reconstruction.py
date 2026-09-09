import hashlib
import importlib
import os
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
JOKES = ROOT / "bot" / "features" / "fun" / "jokes_data.json"
BASE_JOKES_SHA = "dc573e2a954af897350caa4183a98f33d5ed71327fed02c7ebe053d893e3a508"


class V34UtilsTests(unittest.TestCase):
    def test_release_and_docs_are_synchronized(self):
        release = (ROOT / "bot" / "release.py").read_text()
        render = (ROOT / "render.yaml").read_text()
        release_doc = (ROOT / "RELEASE.md").read_text()
        self.assertIn('VERSION = "35.0.0"', release)
        self.assertIn('value: "35.0.0"', render)
        self.assertIn("Version: `35.0.0`", release_doc)

    def test_required_project_files_exist(self):
        for rel in ["requirements.txt", ".env.example", "README.md", "pyproject.toml"]:
            self.assertTrue((ROOT / rel).exists(), rel)
        for rel in [
            "bot/utils/keyboard_factory.py",
            "bot/utils/helpers.py",
            "bot/utils/texts.py",
            "bot/utils/events.py",
            "bot/utils/http_client.py",
            "bot/utils/http_resilience.py",
            "bot/utils/observability.py",
            "bot/utils/task_manager.py",
            "bot/utils/motivation.py",
            "bot/utils/exceptions.py",
        ]:
            self.assertTrue((ROOT / rel).exists(), rel)

    def test_text_contract(self):
        texts = importlib.import_module("bot.utils.texts")
        self.assertIn("fa", texts.SUPPORTED_LANGUAGES)
        self.assertEqual(texts.normalize_language("xx"), "fa")
        self.assertEqual(texts.get_text_for_language("en", "welcome", name="Ali"), "🌟 Hello dear Ali! 🌟")

    def test_event_contract_returns_copies(self):
        events = importlib.import_module("bot.utils.events")
        first = events.get_shamsi_events(1, 1)
        self.assertTrue(first)
        first.append("MUTATION")
        self.assertNotIn("MUTATION", events.get_shamsi_events(1, 1))

    def test_weather_legacy_get_alias(self):
        source = (ROOT / "bot" / "features" / "weather" / "weather.py").read_text()
        self.assertIn("_get = _request_get", source)

    def test_keyboard_registry_is_complete(self):
        keyboards = importlib.import_module("bot.utils.keyboard_factory")
        self.assertEqual(len(keyboards.get_keyboard_builders()), 22)
        self.assertTrue(all(callable(fn) for fn in keyboards.get_keyboard_builders()))

    def test_http_settings_are_typed_and_shared(self):
        http = importlib.import_module("bot.utils.http_client")
        resilience = importlib.import_module("bot.utils.http_resilience")
        self.assertIs(resilience.HTTP_SETTINGS_TYPE, http.HTTPSettings)
        self.assertGreaterEqual(http._SETTINGS.timeout, 0.1)

    def test_ops_helpers_are_bounded(self):
        obs = importlib.import_module("bot.utils.observability")
        tasks = importlib.import_module("bot.utils.task_manager")
        self.assertIsInstance(obs.recent_metrics(limit=5), dict)
        self.assertGreaterEqual(tasks.tracked_task_count(), 0)

    def test_exception_hierarchy(self):
        exc = importlib.import_module("bot.utils.exceptions")
        self.assertTrue(issubclass(exc.RateLimitError, exc.NetworkError))
        self.assertTrue(issubclass(exc.AIQuotaError, exc.AIProviderError))
        self.assertTrue(issubclass(exc.DatabaseError, exc.ALIMJError))

    def test_requirements_are_pinned(self):
        lines = [x.strip() for x in (ROOT / "requirements.txt").read_text().splitlines() if x.strip() and not x.startswith("#")]
        self.assertGreaterEqual(len(lines), 10)
        for line in lines:
            self.assertRegex(line, r"^[A-Za-z0-9_.-]+(?:\[[^]]+\])?==[^=]+$")

    def test_jokes_immutable(self):
        digest = hashlib.sha256(JOKES.read_bytes()).hexdigest()
        self.assertEqual(digest, BASE_JOKES_SHA)

    def test_no_secrets_in_env_example(self):
        env = (ROOT / ".env.example").read_text()
        self.assertNotRegex(env, r"(?i)(api[_-]?key|token)=([^\n]*[^\s])$")


if __name__ == "__main__":
    unittest.main()

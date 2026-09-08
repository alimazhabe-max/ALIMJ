import ast
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JOKES = ROOT / "bot/features/fun/jokes_data.json"


def test_release_is_v30():
    text = (ROOT / "bot/release.py").read_text(encoding="utf-8")
    assert 'VERSION = "30.0.0"' in text
    assert 'RELEASE_CHANNEL = "production"' in text


def test_main_has_startup_self_check_and_safe_health_metadata():
    tree = ast.parse((ROOT / "bot/main.py").read_text(encoding="utf-8"))
    names = {n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    assert "startup_self_check" in names
    assert "health" in names
    text = (ROOT / "bot/main.py").read_text(encoding="utf-8")
    assert "STARTUP_CHECK" in text
    assert '"version": VERSION' in text
    assert "ADMIN_IDS" not in text.split('def health():', 1)[1].split('def run_flask', 1)[0]


def test_render_does_not_override_db_path_and_pins_release_guard():
    text = (ROOT / "render.yaml").read_text(encoding="utf-8")
    assert 'key: DB_PATH' not in text
    assert 'key: STARTUP_CHECK' in text
    assert 'value: "30.0.0"' in text
    assert "Building" in text


def test_jokes_immutable():
    assert hashlib.sha256(JOKES.read_bytes()).hexdigest() == "dc573e2a954af897350caa4183a98f33d5ed71327fed02c7ebe053d893e3a508"

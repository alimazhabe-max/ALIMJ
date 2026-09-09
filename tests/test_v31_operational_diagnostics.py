from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def test_v31_error_buffer_is_bounded_and_exposed():
    text = (ROOT / "bot/utils/observability.py").read_text()
    assert "_ERROR_EVENTS: deque" in text
    assert "maxlen=50" in text
    assert "def record_error" in text
    assert "def recent_errors" in text
    assert '"recent_errors": recent_errors(10)' in text

def test_v31_error_handler_records_failures():
    text = (ROOT / "bot/main.py").read_text()
    assert 'record_error("telegram_update", err)' in text

def test_v31_release():
    text = (ROOT / "bot/release.py").read_text()
    assert 'VERSION = "35.0.0"' in text

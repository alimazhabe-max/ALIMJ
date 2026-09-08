import os
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_tts_voice_is_exported_by_ai_service_facade():
    src = (ROOT / "bot/services/ai_service.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    names = {
        n.targets[0].id
        for n in tree.body
        if isinstance(n, ast.Assign)
        for _ in [n]
        if n.targets and isinstance(n.targets[0], ast.Name)
    }
    assert "TTS_VOICE" in names


def test_ai_media_does_not_reference_missing_tts_facade_symbol():
    src = (ROOT / "bot/services/ai_media.py").read_text(encoding="utf-8")
    assert "TTS_VOICE = _ai.TTS_VOICE" in src
    facade = (ROOT / "bot/services/ai_service.py").read_text(encoding="utf-8")
    assert 'TTS_VOICE = os.getenv("TTS_VOICE", "fa-IR-DilaraNeural")' in facade

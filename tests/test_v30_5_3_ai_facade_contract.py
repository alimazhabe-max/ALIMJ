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


def test_ai_providers_resolve_facade_prompt_helpers_lazily():
    src = (ROOT / "bot/services/ai_providers.py").read_text(encoding="utf-8")
    assert "def _legacy_ai_context()" in src
    assert "return ai_service.SYSTEM_PROMPT, ai_service._messages" in src
    # Provider module must not depend on facade globals at import time; this avoids
    # the V26 circular-import split bug while retaining the full legacy context.
    assert '"text": SYSTEM_PROMPT' not in src
    assert '"messages": _messages(user_id, prompt)' not in src


def test_ai_providers_have_no_unresolved_prompt_symbols():
    src = (ROOT / "bot/services/ai_providers.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}
    assert "SYSTEM_PROMPT" not in names
    assert "_messages" not in names

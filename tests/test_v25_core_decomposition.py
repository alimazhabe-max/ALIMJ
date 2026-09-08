from pathlib import Path
import ast
import hashlib

ROOT = Path(__file__).resolve().parents[1]

def test_media_handlers_extracted_and_facade_preserved():
    impl = ROOT / "bot/handlers/media_handlers.py"
    facade = ROOT / "bot/handlers/messages.py"
    assert impl.exists()
    src = facade.read_text(encoding="utf-8")
    impl_src = impl.read_text(encoding="utf-8")
    assert "from bot.handlers.media_handlers import media_ai_handler as _impl" in src
    assert "from bot.handlers.media_handlers import voice_ai_handler as _impl" in src
    assert "async def media_ai_handler" in impl_src
    assert "async def voice_ai_handler" in impl_src
    # The two heavy implementations should no longer live in messages.py.
    assert src.count("async def media_ai_handler") == 1
    assert src.count("async def voice_ai_handler") == 1
    assert len(src.encode("utf-8")) < 65000


def test_decomposed_module_ast_and_import_surface():
    for rel in ("bot/handlers/messages.py", "bot/handlers/media_handlers.py"):
        ast.parse((ROOT / rel).read_text(encoding="utf-8"))


def test_jokes_immutable_v25():
    p = ROOT / "bot/features/fun/jokes_data.json"
    assert hashlib.sha256(p.read_bytes()).hexdigest() == "dc573e2a954af897350caa4183a98f33d5ed71327fed02c7ebe053d893e3a508"

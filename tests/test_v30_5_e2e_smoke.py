import ast
import pathlib
import sys
import types

ROOT = pathlib.Path(__file__).parents[1]


class _Markup:
    def __init__(self, keyboard=None, **kwargs):
        self.keyboard = keyboard
        self.kwargs = kwargs


class _Button:
    def __init__(self, text, **kwargs):
        self.text = text
        self.kwargs = kwargs


def _install_telegram_stub():
    telegram = types.ModuleType("telegram")
    telegram.InlineKeyboardButton = _Button
    telegram.InlineKeyboardMarkup = _Markup
    telegram.KeyboardButton = _Button
    telegram.ReplyKeyboardMarkup = _Markup
    sys.modules["telegram"] = telegram


def _load_keyboard_factory():
    _install_telegram_stub()
    # Import through the normal package path; no Telegram network is touched.
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    for key in list(sys.modules):
        if key == "bot.utils.keyboard_factory":
            del sys.modules[key]
    import bot.utils.keyboard_factory as factory
    return factory


def test_all_public_keyboard_constructors_execute():
    previous = sys.modules.get("telegram")
    try:
        factory = _load_keyboard_factory()
        names = [
            "get_main_keyboard", "get_ai_keyboard", "get_ai_model_keyboard",
            "get_more_keyboard", "get_date_tools_keyboard", "get_religious_keyboard",
            "get_market_keyboard", "get_weather_geo_keyboard", "get_tools_keyboard",
            "get_azan_keyboard", "get_fun_keyboard", "get_joke_keyboard",
            "get_profile_keyboard", "get_smart_settings_keyboard", "get_country_keyboard",
            "get_iran_cities_keyboard", "get_iraq_cities_keyboard", "get_language_keyboard",
            "get_font_keyboard", "get_font_en_keyboard", "get_font_fa_keyboard",
        ]
        for name in names:
            value = getattr(factory, name)()
            assert value is not None, name
            assert hasattr(value, "keyboard"), name
            assert value.keyboard, name
    finally:
        if previous is None:
            sys.modules.pop("telegram", None)
        else:
            sys.modules["telegram"] = previous


def test_messages_exposes_legacy_facade_handlers():
    source = (ROOT / "bot" / "handlers" / "messages.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    functions = {n.name for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    assert {"text_handler", "media_ai_handler", "voice_ai_handler", "lens_command"} <= functions


def test_main_contains_executing_runtime_smoke_not_only_callable_checks():
    source = (ROOT / "bot" / "main.py").read_text(encoding="utf-8")
    assert "smoke_keyboards" in source
    assert "constructor()" in source
    assert "Runtime smoke failed for keyboard:" in source

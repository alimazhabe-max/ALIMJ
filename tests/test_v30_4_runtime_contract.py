import ast
import pathlib


def _handler_targets(source: str):
    tree = ast.parse(source)
    targets = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr != "add_handler" or not node.args:
            continue
        handler = node.args[0]
        if not isinstance(handler, ast.Call) or not isinstance(handler.func, ast.Name):
            continue
        kind = handler.func.id
        index = {"CommandHandler": 1, "MessageHandler": 1, "CallbackQueryHandler": 0}.get(kind)
        if index is not None and len(handler.args) > index and isinstance(handler.args[index], ast.Name):
            targets.append(handler.args[index].id)
    return targets


def test_main_handler_targets_are_imported():
    root = pathlib.Path(__file__).parents[1]
    main = (root / "bot" / "main.py").read_text(encoding="utf-8")
    tree = ast.parse(main)
    imported = set()
    for node in tree.body:
        if isinstance(node, ast.ImportFrom):
            imported.update(a.asname or a.name for a in node.names)
    missing = sorted(set(_handler_targets(main)) - imported)
    assert not missing, f"Handler targets not imported in main.py: {missing}"


def test_startup_self_check_covers_ui_contracts():
    source = (pathlib.Path(__file__).parents[1] / "bot" / "main.py").read_text(encoding="utf-8")
    for name in ("required_keyboards", "required_features", "keyboard:", "feature:"):
        assert name in source

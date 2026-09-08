import ast
import builtins
import pathlib
import symtable


def _unresolved_globals(path: pathlib.Path):
    table = symtable.symtable(path.read_text(encoding="utf-8"), str(path), "exec")
    builtin_names = set(dir(builtins))
    unresolved = []
    for symbol in table.get_symbols():
        name = symbol.get_name()
        if name in builtin_names or name.startswith("__"):
            continue
        if symbol.is_global() and symbol.is_referenced() and not symbol.is_imported() and not symbol.is_assigned() and not symbol.is_parameter():
            unresolved.append(name)
    return unresolved


def test_no_unresolved_global_names_in_bot_modules():
    root = pathlib.Path(__file__).parents[1] / "bot"
    failures = {}
    for path in root.rglob("*.py"):
        ast.parse(path.read_text(encoding="utf-8"))
        unresolved = _unresolved_globals(path)
        if unresolved:
            failures[str(path)] = sorted(unresolved)
    assert not failures, "Unresolved global names: " + repr(failures)

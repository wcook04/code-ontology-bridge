"""Calls follow Python's scopes: an import binds only where it is written, and a
nested function's body is not code its enclosing function runs."""

import json
from pathlib import Path

from code_ontology_bridge.codemap import build_code_map


def _edges(root: Path) -> set[tuple[str, str | None]]:
    rows = build_code_map(root).rows["calls"]
    return {(r["caller_symbol_id"], r["callee_symbol_id"]) for r in rows}


def test_function_local_imports_resolve_in_their_own_function(tmp_path: Path) -> None:
    (tmp_path / "foo.py").write_text("def target():\n    pass\n")
    (tmp_path / "bar.py").write_text("def target():\n    pass\n")
    (tmp_path / "consumer.py").write_text(
        "def f():\n    from foo import target\n    target()\n\n"
        "def g():\n    from bar import target\n    target()\n\n"
        "def h():\n    target()\n"
    )
    edges = _edges(tmp_path)
    assert ("consumer.py::f", "foo.py::target") in edges
    assert ("consumer.py::g", "bar.py::target") in edges
    assert ("consumer.py::f", "bar.py::target") not in edges
    # h imports nothing, and neither function's import is visible to it.
    assert ("consumer.py::h", "foo.py::target") not in edges
    assert ("consumer.py::h", "bar.py::target") not in edges


def test_module_import_is_overridden_inside_a_function_that_imports_the_same_name(tmp_path: Path) -> None:
    (tmp_path / "foo.py").write_text("def target():\n    pass\n")
    (tmp_path / "bar.py").write_text("def target():\n    pass\n")
    (tmp_path / "consumer.py").write_text(
        "from foo import target\n\n"
        "def f():\n    target()\n\n"
        "def g():\n    from bar import target\n    target()\n"
    )
    edges = _edges(tmp_path)
    assert ("consumer.py::f", "foo.py::target") in edges
    assert ("consumer.py::g", "bar.py::target") in edges
    assert ("consumer.py::g", "foo.py::target") not in edges


def test_calls_in_a_nested_function_body_are_not_calls_of_the_enclosing_function(tmp_path: Path) -> None:
    (tmp_path / "nested.py").write_text(
        "def other():\n    pass\n\n"
        "def deco():\n    return lambda fn: fn\n\n"
        "def outer():\n"
        "    @deco()\n"
        "    def never_called():\n"
        "        other()\n"
        "    return 42\n"
    )
    code_map = build_code_map(tmp_path)
    edges = {(r["caller_symbol_id"], r["callee_symbol_id"]) for r in code_map.rows["calls"]}
    assert ("nested.py::outer", "nested.py::other") not in edges
    # The decorator factory is called when outer runs, so that call is outer's.
    assert ("nested.py::outer", "nested.py::deco") in edges
    assert any("nested functions" in limit and "(1 in this snapshot)" in limit for limit in json.loads(code_map.snapshot["known_limits"]))


def test_a_nested_function_the_enclosing_function_calls_keeps_its_calls(tmp_path: Path) -> None:
    (tmp_path / "helper.py").write_text(
        "def other():\n    pass\n\n"
        "def outer():\n"
        "    def inner():\n"
        "        other()\n"
        "    return inner()\n\n"
        "def deco(fn):\n"
        "    def wrapper():\n"
        "        other()\n"
        "        return fn()\n"
        "    return wrapper\n"
    )
    edges = _edges(tmp_path)
    # outer runs inner, so outer reaches other.
    assert ("helper.py::outer", "helper.py::other") in edges
    # deco only returns wrapper; the decorated function's caller runs it, not deco.
    assert ("helper.py::deco", "helper.py::other") not in edges


def test_a_chain_of_nested_functions_run_by_the_enclosing_function_keeps_its_calls(tmp_path: Path) -> None:
    (tmp_path / "chain.py").write_text(
        "def other():\n    pass\n\n"
        "def outer():\n"
        "    def build():\n"
        "        other()\n"
        "    def run():\n"
        "        build()\n"
        "    run()\n"
    )
    assert ("chain.py::outer", "chain.py::other") in _edges(tmp_path)

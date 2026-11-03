import hashlib
import json
from pathlib import Path

import pytest

from code_ontology_bridge.codemap import build_code_map
from code_ontology_bridge.codemap.schema import TABLES

FILES = {
    "pkg/__init__.py": '"""[PURPOSE]\n- Teleology: A tiny package.\n"""\nfrom .a import f as exported_f\n',
    "pkg/a.py": '''"""Helpers for the tiny package.

Second paragraph.
"""


def f():
    return 1


def g():
    return f() + len([])


class Base:
    def inherited(self):
        return 0


class C(Base):
    """A class."""

    def m(self):
        self.n()
        self.inherited()
        return self.missing()

    def n(self):
        return C.m(self)

    def _private(self):
        def inner():
            return f()
        return inner()


print("module level")
''',
    "pkg/b.py": '''from .a import f
from pkg import a
import pkg.a
from pkg import exported_f
import os
import logging
from typing import cast as typing_cast

logger = logging.getLogger(__name__)
LOCAL = dict(a=1)


def h():
    f()
    a.f()
    pkg.a.g()
    exported_f()
    os.path.join("x")
''',
    "pkg/sub/__init__.py": "",
    "pkg/sub/c.py": '''from ..a import C


class D(C):
    def run(self):
        return self.inherited()
''',
    "pkg/kinds.py": '''import logging

from pkg.a import C

log = logging.getLogger(__name__)
helper = C()


def k(row, callback, items):
    log.info("x")
    row.get("a")
    helper.m()
    items[0].run()
    callback()
    str.join(",", [])
    dict(a=1)
    C.missing_classmethod()
    super().__init__()
    (lambda: 1)()


class E:
    def go(self):
        self.client.send()
''',
    "pkg/workers.py": '''import asyncio
import functools
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Generic

from pkg.a import Base, C, f, g


def job(n):
    return n


class Runner(Base):
    async def run_once(self, name):
        value = await asyncio.to_thread(job, name)
        threading.Thread(target=self.tick, daemon=True).start()
        with ThreadPoolExecutor() as pool:
            pool.submit(g)
        return functools.partial(f, value)

    def tick(self):
        handler = job
        sorted([], key=handler)
        isinstance(self, C)
        getattr(job, "__name__")
        max([1], default=self.size)
        return self.inherited

    @property
    def size(self):
        return 1


def uses_param(job):
    return asyncio.to_thread(job)


class Mixed(Runner, dict, Generic[int]):
    pass
''',
    "tests/test_a.py": '''from pkg.a import f


def test_f():
    assert f() == 1
''',
    "tests/test_b.py": "def test_nothing():\n    pass\n",
    "broken.py": "def oops(:\n",
}


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    for rel, text in FILES.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    return tmp_path


def _calls(code_map, caller, kind="direct"):
    return [
        (c["callee_name"], c["callee_symbol_id"], c["resolution"], c["confidence"])
        for c in code_map.rows["calls"]
        if c["caller_symbol_id"] == caller and c["call_kind"] == kind
    ]


def test_files_modules_and_descriptions(repo):
    m = build_code_map(repo, repo_url="https://example.invalid/r", commit_sha="abc123")
    files = {f["file_id"]: f for f in m.rows["files"]}
    assert files["pkg/__init__.py"]["module"] == "pkg"
    assert files["pkg/__init__.py"]["package"] == "pkg"
    assert files["pkg/sub/c.py"]["module"] == "pkg.sub.c"
    assert files["pkg/sub/c.py"]["package"] == "pkg.sub"
    assert (files["pkg/__init__.py"]["description"], files["pkg/__init__.py"]["description_source"]) == ("A tiny package.", "heading_purpose")
    assert files["pkg/__init__.py"]["has_fixed_headings"] is True
    assert (files["pkg/a.py"]["description"], files["pkg/a.py"]["description_source"]) == ("Helpers for the tiny package.", "module_docstring")
    assert (files["pkg/b.py"]["description"], files["pkg/b.py"]["description_source"]) == ("", "none")
    assert files["tests/test_a.py"]["is_test"] and not files["pkg/a.py"]["is_test"]
    assert files["pkg/a.py"]["sha256"] == hashlib.sha256((repo / "pkg/a.py").read_bytes()).hexdigest()
    headings = [(h["heading"], h["value"]) for h in m.rows["headings"] if h["file_id"] == "pkg/__init__.py"]
    assert headings == [("[PURPOSE]", "- Teleology: A tiny package."), ("Teleology", "A tiny package.")]


def test_unparseable_file_is_counted_not_dropped(repo):
    m = build_code_map(repo, commit_sha="abc123")
    assert "broken.py" not in {f["file_id"] for f in m.rows["files"]}
    assert m.snapshot["omitted_file_count"] == 1
    assert m.omitted_files == [{"file_id": "broken.py", "reason": "parse_error: SyntaxError"}]
    assert any("not analysed" in limit for limit in json.loads(m.snapshot["known_limits"]))


def test_symbols(repo):
    m = build_code_map(repo, commit_sha="abc123")
    symbols = {s["symbol_id"]: s for s in m.rows["symbols"]}
    assert symbols["pkg/a.py::C.m"]["kind"] == "method"
    assert symbols["pkg/a.py::C"]["kind"] == "class"
    assert symbols["pkg/a.py::C"]["summary"] == "A class."
    assert symbols["pkg/a.py::f"]["summary_source"] == "none"
    assert symbols["pkg/a.py::C._private"]["is_public"] is False
    assert "pkg/a.py::C._private.inner" not in symbols  # nested functions are not symbols


def test_call_resolution(repo):
    m = build_code_map(repo, commit_sha="abc123")
    assert set(_calls(m, "pkg/a.py::g")) == {
        ("f", "pkg/a.py::f", "same_file", "high"),
        ("len", None, "builtin", "high"),
    }
    assert set(_calls(m, "pkg/a.py::C.m")) == {
        ("self.n", "pkg/a.py::C.n", "method_on_self", "high"),
        ("self.inherited", "pkg/a.py::Base.inherited", "method_on_self", "low"),
        ("self.missing", None, "unresolved", "low"),
    }
    assert ("C.m", "pkg/a.py::C.m", "same_file", "high") in _calls(m, "pkg/a.py::C.n")
    # The nested function's call is attributed to the enclosing method.
    assert ("f", "pkg/a.py::f", "same_file", "high") in _calls(m, "pkg/a.py::C._private")
    assert set(_calls(m, "pkg/b.py::h")) == {
        ("f", "pkg/a.py::f", "imported", "high"),
        ("a.f", "pkg/a.py::f", "imported", "high"),
        ("pkg.a.g", "pkg/a.py::g", "imported", "high"),
        ("exported_f", "pkg/a.py::f", "imported", "high"),  # re-export through pkg/__init__.py
        ("os.path.join", None, "external", "high"),
    }
    # Inherited through a base class imported from another module.
    assert _calls(m, "pkg/sub/c.py::D.run") == [("self.inherited", "pkg/a.py::Base.inherited", "method_on_self", "low")]
    assert any("Calls at module level" in limit and "(5 in" in limit for limit in json.loads(m.snapshot["known_limits"]))


def test_non_internal_calls_are_classified_never_guessed(repo):
    m = build_code_map(repo, commit_sha="abc123")
    assert sorted(_calls(m, "pkg/kinds.py::k")) == sorted([
        ("log.info", None, "external", "high"),  # module-level log = logging.getLogger(...)
        ("row.get", None, "dynamic_attribute", "low"),
        ("helper.m", None, "dynamic_attribute", "low"),  # internal type, but not tracked: no guess
        ("<expr>.run", None, "dynamic_attribute", "low"),
        ("callback", None, "unresolved", "low"),
        ("str.join", None, "builtin", "high"),
        ("dict", None, "builtin", "high"),
        ("C.missing_classmethod", None, "dynamic_attribute", "low"),
        ("<expr>.__init__", None, "dynamic_attribute", "low"),
        ("super", None, "builtin", "high"),
        ("<expr>", None, "unresolved", "low"),
    ])
    assert _calls(m, "pkg/kinds.py::E.go") == [("self.client.send", None, "dynamic_attribute", "low")]
    # Only internal kinds carry a callee.
    for c in m.rows["calls"]:
        assert (c["callee_symbol_id"] is not None) == (c["resolution"] in ("same_file", "imported", "method_on_self"))


def test_callback_references(repo):
    m = build_code_map(repo, commit_sha="abc123")
    assert sorted(_calls(m, "pkg/workers.py::Runner.run_once", "callback")) == sorted([
        ("job", "pkg/workers.py::job", "same_file", "low"),  # asyncio.to_thread(job, name)
        ("self.tick", "pkg/workers.py::Runner.tick", "method_on_self", "low"),  # Thread(target=self.tick)
        ("g", "pkg/a.py::g", "imported", "low"),  # pool.submit(g)
        ("f", "pkg/a.py::f", "imported", "low"),  # functools.partial(f, value)
    ])
    # Local names, self, classes, properties and arguments of examining builtins are not callbacks.
    assert _calls(m, "pkg/workers.py::Runner.tick", "callback") == []
    # A parameter that shadows a module-level function is not the function.
    assert _calls(m, "pkg/workers.py::uses_param", "callback") == []
    # The direct calls at the same sites are unchanged.
    assert ("asyncio.to_thread", None, "external", "high") in _calls(m, "pkg/workers.py::Runner.run_once")
    for c in m.rows["calls"]:
        if c["call_kind"] == "callback":
            assert c["callee_symbol_id"] and c["confidence"] == "low"
            assert c["resolution"] in ("same_file", "imported", "method_on_self")
    call = next(c for c in m.rows["calls"] if c["call_kind"] == "callback" and c["callee_name"] == "job")
    assert call["call_id"] == "pkg/workers.py:16:40:0" and call["line"] == 16
    assert m.stats["calls"]["by_call_kind"]["callback"] == 4


def test_class_bases(repo):
    m = build_code_map(repo, commit_sha="abc123")
    bases = {(b["class_symbol_id"], b["ordinal"]): (b["base_name"], b["base_symbol_id"]) for b in m.rows["class_bases"]}
    assert bases[("pkg/a.py::C", 1)] == ("Base", "pkg/a.py::Base")
    assert bases[("pkg/sub/c.py::D", 1)] == ("C", "pkg/a.py::C")  # through an import
    assert bases[("pkg/workers.py::Runner", 1)] == ("Base", "pkg/a.py::Base")
    assert [bases[("pkg/workers.py::Mixed", i)] for i in (1, 2, 3)] == [
        ("Runner", "pkg/workers.py::Runner"),
        ("dict", None),
        ("Generic[int]", None),
    ]
    assert ("pkg/a.py::Base", 1) not in bases


def test_imports_and_test_links(repo):
    m = build_code_map(repo, commit_sha="abc123")
    imports = {(i["file_id"], i["module_name"], i["imported_file_id"], i["is_internal"]) for i in m.rows["imports"]}
    assert ("pkg/b.py", "pkg.a", "pkg/a.py", True) in imports
    assert ("pkg/b.py", "os", None, False) in imports
    assert ("pkg/sub/c.py", "pkg.a", "pkg/a.py", True) in imports
    assert ("pkg/__init__.py", "pkg.a", "pkg/a.py", True) in imports
    links = {(t["test_file_id"], t["target_file_id"], t["reason"]) for t in m.rows["test_links"]}
    assert links == {
        ("tests/test_a.py", "pkg/a.py", "imports_target"),
        ("tests/test_a.py", "pkg/a.py", "name_match"),
        ("tests/test_b.py", "pkg/b.py", "name_match"),
    }


def test_snapshot_identity_and_determinism(repo, monkeypatch):
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1700000000")
    one = build_code_map(repo, repo_url="u", commit_sha="abc123")
    two = build_code_map(repo, repo_url="u", commit_sha="abc123")
    assert one.rows == two.rows and one.snapshot == two.snapshot
    s = one.snapshot
    assert s["built_at"] == "2023-11-14T22:13:20Z"
    assert s["file_count"] == len(one.rows["files"])
    # Fingerprint: 16 hex of sha256 over sorted "path NUL sha256 \n" lines (governance's algorithm).
    digest = hashlib.sha256()
    for f in sorted(r["file_id"] for r in one.rows["files"]):
        digest.update(f.encode() + b"\0" + hashlib.sha256((repo / f).read_bytes()).hexdigest().encode() + b"\n")
    assert s["source_fingerprint"] == digest.hexdigest()[:16]
    assert s["snapshot_id"] == f"abc123-{s['source_fingerprint'][:12]}"
    for table in TABLES:
        keys = [tuple(r[c] for c in table.primary_key) for r in one.rows[table.name]]
        assert len(keys) == len(set(keys)), table.name


def test_editing_a_file_moves_the_fingerprint(repo):
    before = build_code_map(repo, commit_sha="x").snapshot["source_fingerprint"]
    (repo / "pkg/b.py").write_text((repo / "pkg/b.py").read_text() + "\n# edit\n")
    assert build_code_map(repo, commit_sha="x").snapshot["source_fingerprint"] != before


def test_exclude_is_counted(repo):
    m = build_code_map(repo, commit_sha="x", exclude=["tests/*"])
    assert {o["file_id"] for o in m.omitted_files} == {"broken.py", "tests/test_a.py", "tests/test_b.py"}
    assert m.snapshot["omitted_file_count"] == 3

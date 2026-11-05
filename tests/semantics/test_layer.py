"""The semantics layer views agree with independent Python computations on random code maps."""

from __future__ import annotations

import random
from collections import deque

import duckdb
import pytest

from code_ontology_bridge.codemap.schema import SCHEMA, TABLES, create_table_sql
from code_ontology_bridge.semantics import LAYER_VIEWS, install_layer, layer_context_text


def random_map(seed: int):
    rng = random.Random(seed)
    files = [f"pkg/sub{i % 3}/m{i}.py" for i in range(5)] + ["top.py", "tests/test_m0.py"]
    symbols = []
    for i in range(rng.randint(6, 30)):
        f = rng.choice(files)
        kind = rng.choice(["function", "function", "method", "class"])
        qual = f"C{i}.f{i}" if kind == "method" else f"s{i}"
        symbols.append((f"{f}::{qual}", f, qual.split(".")[-1], qual, kind, rng.random() < 0.7, rng.random() < 0.5))
    ids = [s[0] for s in symbols]
    calls = []
    for j in range(rng.randint(0, 80)):
        a, b = rng.choice(ids), rng.choice(ids)
        kind = "direct" if rng.random() < 0.75 else "callback"
        calls.append((f"c{j}", a, b, kind, rng.randint(1, 200)))
    for j in range(rng.randint(0, 10)):  # unresolved direct calls carry no callee
        calls.append((f"u{j}", rng.choice(ids), None, "direct", 5))
    classes = [s[0] for s in symbols if s[4] == "class"]
    bases = []
    for c in classes:
        for o in range(rng.randint(0, 2)):
            bases.append((c, o + 1, rng.choice(classes + [None])))
    return files, symbols, calls, bases


def load(seed: int):
    files, symbols, calls, bases = random_map(seed)
    con = duckdb.connect()
    con.execute(f"CREATE SCHEMA {SCHEMA}")
    for t in TABLES:
        con.execute(create_table_sql(t, inline_foreign_keys=False))
    for f in files:
        con.execute("INSERT INTO code.files VALUES (?, '', ?, ?, 10, 'x', '', 'none', false)",
                    [f, f.removesuffix(".py").replace("/", "."), f.startswith("tests/")])
    for sid, f, name, qual, kind, public, doc in symbols:
        con.execute("INSERT INTO code.symbols VALUES (?, ?, ?, ?, ?, 1, 9, ?, '', ?)",
                    [sid, f, name, qual, kind, public, "docstring" if doc else "none"])
    for cid, a, b, kind, line in calls:
        res = "same_file" if b else "unresolved"
        conf = "low" if kind == "callback" or not b else "high"
        con.execute("INSERT INTO code.calls VALUES (?, ?, ?, 'x', ?, ?, ?, ?)", [cid, a, b, line, res, conf, kind])
    for c, o, b in bases:
        con.execute("INSERT INTO code.class_bases VALUES (?, ?, 'B', ?)", [c, o, b])
    install_layer(con)
    return con, calls, bases


def shortest(edges, src_targets):
    """BFS from every caller over (caller -> callee) edges; returns {(caller, target): depth}, no self pairs."""
    out = {}
    nodes = {a for a, _ in edges}
    adj = {}
    for a, b in edges:
        adj.setdefault(a, set()).add(b)
    for s in nodes:
        seen, q = {s: 0}, deque([s])
        while q:
            u = q.popleft()
            for v in adj.get(u, ()):
                if v not in seen:
                    seen[v] = seen[u] + 1
                    q.append(v)
        for v, d in seen.items():
            if v != s:
                out[(s, v)] = d
    return out


@pytest.mark.parametrize("seed", range(60))
def test_reachability_matches_bfs(seed):
    con, calls, _ = load(seed)
    edges_any = {(a, b) for _, a, b, _, _ in calls if b and a != b}
    edges_direct = {(a, b) for _, a, b, k, _ in calls if b and a != b and k == "direct"}
    want_any, want_direct = shortest(edges_any, None), shortest(edges_direct, None)
    got = {(a, b): (d, x) for a, b, d, x in con.execute(
        "SELECT caller_symbol_id, target_symbol_id, direct_depth, any_depth FROM code.reachability").fetchall()}
    assert set(got) == set(want_any)
    for pair, (d, x) in got.items():
        assert x == want_any[pair]
        assert d == want_direct.get(pair)


@pytest.mark.parametrize("seed", range(30))
def test_call_edges_and_profile_counts(seed):
    con, calls, _ = load(seed)
    pairs = {}
    for _, a, b, k, _ in calls:
        if b:
            pairs.setdefault((a, b), [0, 0])[0 if k == "direct" else 1] += 1
    got = {(a, b): [d, c] for a, b, d, c in con.execute(
        "SELECT caller_symbol_id, callee_symbol_id, direct_call_sites, callback_references FROM code.call_edges").fetchall()}
    assert got == pairs
    direct_callers = {}
    for (a, b), (d, _) in pairs.items():
        if d and a != b:
            direct_callers.setdefault(b, set()).add(a)
    for sid, n in con.execute("SELECT symbol_id, direct_callers FROM code.symbol_profile").fetchall():
        assert n == len(direct_callers.get(sid, ()))


@pytest.mark.parametrize("seed", range(30))
def test_class_ancestry_matches_bfs(seed):
    con, _, bases = load(seed)
    want = shortest({(c, b) for c, _, b in bases if b and b != c}, None)
    got = {(a, b): d for a, b, d in con.execute("SELECT * FROM code.class_ancestry").fetchall()}
    assert got == want


def test_directory_is_the_folder_not_the_module():
    con, _, _ = load(1)
    rows = dict(con.execute("SELECT file_id, directory FROM code.file_profile").fetchall())
    assert rows["top.py"] == ""
    assert rows["pkg/sub0/m0.py"] == "pkg/sub0"
    assert rows["tests/test_m0.py"] == "tests"


def test_every_view_column_is_documented():
    con, _, _ = load(2)
    for v in LAYER_VIEWS:
        cols = [r[0] for r in con.execute(f"DESCRIBE {v.qualified}").fetchall()]
        assert cols == [c for c, _ in v.columns], v.name
    assert "code.reachability" in layer_context_text()

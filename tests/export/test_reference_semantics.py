"""The reference queries must answer their question on any code, not only on the frozen
example: here the recursive caller reference (question 11) runs on a synthetic repository
with a long chain, a cycle, two paths to one caller and a test-file caller."""

import json
from pathlib import Path

import duckdb

from code_ontology_bridge.codemap import build_code_map
from code_ontology_bridge.export import export_duckdb

REPO = Path(__file__).resolve().parents[2]
QUESTIONS = {q["question_id"]: q for q in json.loads((REPO / "eval" / "auto_ontology_questions.json").read_text())}


def _db(tmp_path: Path) -> Path:
    src = tmp_path / "src"
    (src / "tests").mkdir(parents=True)
    # target <- c1 <- c2 <- ... <- c7 (a chain seven deep), with c7 also calling c6's caller loop back.
    body = ["def target():\n    pass\n"]
    for i in range(1, 8):
        callee = "target" if i == 1 else f"c{i - 1}"
        body.append(f"def c{i}():\n    {callee}()\n")
    # A cycle: a calls b, b calls a, and b calls target.
    body.append("def a():\n    b()\n")
    body.append("def b():\n    a()\n    target()\n")
    # Two paths to one caller: m calls c1 (depth 2) and c3 (depth 4); its shortest depth is 2.
    body.append("def m():\n    c1()\n    c3()\n")
    (src / "mod.py").write_text("\n".join(body))
    (src / "tests" / "test_mod.py").write_text("from mod import target\n\ndef test_target():\n    target()\n")
    out = tmp_path / "synthetic.duckdb"
    export_duckdb(build_code_map(src), out)
    return out


def test_question_11_reference_finds_every_caller_at_its_shortest_depth(tmp_path: Path) -> None:
    sql = QUESTIONS[11]["SQL"].replace("'resolve_semantic_fks'", "'target'")
    con = duckdb.connect(str(_db(tmp_path)), read_only=True)
    rows = dict(con.execute(sql).fetchall())
    expected = {f"mod.py::c{i}": i for i in range(1, 8)}
    expected.update({"mod.py::b": 1, "mod.py::a": 2, "mod.py::m": 2})
    assert rows == expected
    assert "tests/test_mod.py::test_target" not in rows

import json
import shutil
import subprocess

import duckdb
import pytest

from code_ontology_bridge.codemap.schema import TABLES, VIEWS
from code_ontology_bridge.export import export_duckdb

from .conftest import CORRECTIONS, EXAMPLE, needs_clone


def test_refuses_a_file_named_code(tmp_path, worked_example):
    with pytest.raises(ValueError):
        export_duckdb(worked_example.code_map, tmp_path / "code.duckdb")


@needs_clone
def test_schema_keys_and_views(worked_example):
    con = duckdb.connect(str(worked_example.duckdb), read_only=True)
    try:
        constraints = con.execute(
            "SELECT table_name, constraint_type, COUNT(*) FROM information_schema.table_constraints "
            "WHERE table_schema = 'code' AND constraint_type IN ('PRIMARY KEY', 'FOREIGN KEY') GROUP BY ALL"
        ).fetchall()
        got = {(t, k): n for t, k, n in constraints}
        for table in TABLES:
            assert got.get((table.name, "PRIMARY KEY")) == 1, table.name
            assert got.get((table.name, "FOREIGN KEY"), 0) == len(table.foreign_keys), table.name
        views = {r[0] for r in con.execute("SELECT table_name FROM information_schema.views WHERE table_schema = 'code'").fetchall()}
        assert views == {v.name for v in VIEWS}
        for table in TABLES:
            n = con.execute(f"SELECT COUNT(*) FROM {table.qualified}").fetchone()[0]
            assert n == len(worked_example.code_map.rows[table.name])
        # NULLs survive the CSV round trip; empty strings stay empty strings.
        assert con.execute("SELECT COUNT(*) FROM code.calls WHERE callee_symbol_id IS NULL").fetchone()[0] == sum(
            1 for c in worked_example.code_map.rows["calls"] if c["callee_symbol_id"] is None
        )
        assert con.execute("SELECT COUNT(*) FROM code.files WHERE description = ''").fetchone()[0] == sum(
            1 for f in worked_example.code_map.rows["files"] if f["description"] == ""
        )
    finally:
        con.close()


@needs_clone
def test_foreign_keys_are_enforced(worked_example, tmp_path):
    import shutil

    copy = tmp_path / "copy.duckdb"
    shutil.copy(worked_example.duckdb, copy)
    con = duckdb.connect(str(copy))
    try:
        with pytest.raises(duckdb.ConstraintException):
            con.execute("INSERT INTO code.symbols VALUES ('nope.py::x', 'nope.py', 'x', 'x', 'function', 1, 1, true, '', 'none')")
    finally:
        con.close()


@needs_clone
def test_their_duckdb_connector_reads_our_file(worked_example, their_duckdb_connector):
    db = their_duckdb_connector(f"duckdb://{worked_example.duckdb}")
    try:
        assert db.dialect == "duckdb"
        assert db.database_name == "auto_ontology_code"
        tables = db.get_tables()
        code_tables = set(tables[tables.table_schema == "code"].table_name)
        assert {t.name for t in TABLES} | {v.name for v in VIEWS} <= code_tables
        columns = db.get_columns()
        files_cols = list(columns[(columns.table_schema == "code") & (columns.table_name == "files")].column_name)
        assert files_cols == [c.name for c in TABLES[1].columns]
        views = db.get_views()
        assert set(views[views.table_schema == "code"].table_name) == {v.name for v in VIEWS}
        frame = db.execute("SELECT caller_symbol_id FROM code.calls c JOIN code.symbols s ON s.symbol_id = c.callee_symbol_id WHERE s.name = 'upsert_table_term' ORDER BY 1")
        assert "auto_ontology/semantic/visit_enter.py::_commit_terms" in list(frame.caller_symbol_id)
        # Their connector reports no keys (documented gap); the file itself declares them.
        assert db.get_pks().empty and db.get_fks().empty
    finally:
        db.close()


def _table_rows(path):
    con = duckdb.connect(str(path), read_only=True)
    try:
        return {
            t.name: con.execute(f"SELECT * FROM {t.qualified} ORDER BY {', '.join(t.primary_key)}").fetchall()
            for t in TABLES
        }
    finally:
        con.close()


@needs_clone
def test_rebuild_gives_identical_rows(worked_example, tmp_path):
    """The DuckDB bytes may differ between builds; the rows may not. Checked
    against a second export and, when present, the committed example file."""
    first = _table_rows(worked_example.duckdb)
    assert first == _table_rows(export_duckdb(worked_example.code_map, tmp_path / "again.duckdb"))
    committed = EXAMPLE / "auto_ontology_code.duckdb"
    if committed.is_file():
        frozen = _table_rows(committed)
        for name, rows in first.items():
            change = CORRECTIONS["tables"].get(f"code.{name}.csv")
            if change is None:
                assert frozen[name] == rows, name
            else:  # exact rows are compared in test_dataset; here the counts must agree
                assert len(frozen[name]) - len(change["removed"]) + len(change["added"]) == len(rows), name


THEIR_DUCKDB = "1.5.5"  # the minimum Auto Ontology pins (pyproject: duckdb>=1.5.5)


@needs_clone
@pytest.mark.skipif(shutil.which("uv") is None, reason="needs uv to run their DuckDB version")
def test_their_pinned_duckdb_opens_the_file(worked_example):
    probe = (
        "import duckdb, json, sys; c = duckdb.connect(sys.argv[1], read_only=True); "
        "print(json.dumps([duckdb.__version__, c.sql(\"select count(*) from duckdb_tables() where schema_name='code'\").fetchone()[0], "
        "c.sql(\"select count(*) from duckdb_constraints() where schema_name='code' and constraint_type in ('PRIMARY KEY','FOREIGN KEY')\").fetchone()[0]]))"
    )
    out = subprocess.run(
        ["uv", "run", "--no-project", "--with", f"duckdb=={THEIR_DUCKDB}", "python", "-c", probe, str(worked_example.duckdb)],
        capture_output=True, text=True, timeout=300,
    )
    if out.returncode != 0 and "Failed to fetch" in out.stderr:
        pytest.skip("uv could not download duckdb (offline)")
    assert out.returncode == 0, out.stderr
    version, tables, keys = json.loads(out.stdout.strip().splitlines()[-1])
    assert version == THEIR_DUCKDB
    assert tables == len(TABLES)
    assert keys == len(TABLES) + sum(len(t.foreign_keys) for t in TABLES)

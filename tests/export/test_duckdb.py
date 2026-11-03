import duckdb
import pytest

from code_ontology_bridge.codemap.schema import TABLES, VIEWS
from code_ontology_bridge.export import export_duckdb

from .conftest import EXAMPLE, needs_clone


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
        assert _table_rows(committed) == first

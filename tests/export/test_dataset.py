"""The ontology-sql-eval dataset folder, its gold SQL on DuckDB, and the same folder seeded into Postgres."""

import json
import math
from decimal import Decimal
from pathlib import Path

import duckdb
import pytest

from code_ontology_bridge.codemap.schema import TABLES
from code_ontology_bridge.export.dataset_export import run_query

from .conftest import ANALYSES, EXAMPLE, NAME, QUESTIONS, needs_clone

EVAL_KEYS = ["question_id", "db_id", "question", "evidence", "SQL", "difficulty", "answer_raw", "answer"]


def test_questions_are_well_formed():
    assert 15 <= len(QUESTIONS) <= 25
    assert len({q["question_id"] for q in QUESTIONS}) == len(QUESTIONS)
    assert {q["difficulty"] for q in QUESTIONS} == {"simple", "moderate", "challenging"}
    assert 4 <= len(ANALYSES) <= 8
    assert all(set(a) == {"name", "description", "sql"} for a in ANALYSES)


@needs_clone
def test_layout(worked_example):
    d = worked_example.dataset
    assert sorted(p.name for p in (d / "ddl").iterdir()) == ["01_schemas.sql", "03_tables.sql", "05_fkeys.sql", "06_views.sql"]
    assert sorted(p.name for p in (d / "data").iterdir()) == sorted(f"code.{t.name}.csv" for t in TABLES)
    evaluation = json.loads((d / "evaluation.json").read_text())
    assert [list(e) for e in evaluation] == [EVAL_KEYS] * len(QUESTIONS)
    assert {e["db_id"] for e in evaluation} == {NAME.upper()}
    assert all(isinstance(e["answer_raw"], str) and isinstance(e["answer"], str) for e in evaluation)
    assert "FOREIGN KEY" not in (d / "ddl" / "03_tables.sql").read_text()
    calls_csv = (d / "data" / "code.calls.csv").read_text().splitlines()
    assert calls_csv[0] == "call_id,caller_symbol_id,callee_symbol_id,callee_name,line,resolution,confidence,call_kind"
    assert any(",\\N," in line for line in calls_csv[1:])


@needs_clone
def test_gold_sql_runs_non_empty_and_deterministic(worked_example):
    con = duckdb.connect(str(worked_example.duckdb), read_only=True)
    try:
        for q in QUESTIONS:
            first = run_query(con, q["SQL"])
            assert first, f"question {q['question_id']} returned no rows"
            assert run_query(con, q["SQL"]) == first
        for a in ANALYSES:
            assert run_query(con, a["sql"]), a["name"]
    finally:
        con.close()


@needs_clone
def test_committed_worked_example_matches_a_fresh_build(worked_example):
    """examples/auto-ontology is reproducible: same rows, same gold answers."""
    committed = EXAMPLE / NAME
    if not committed.is_dir():
        pytest.skip("worked example not generated")
    for table in TABLES:
        name = f"code.{table.name}.csv"
        assert (committed / "data" / name).read_bytes() == (worked_example.dataset / "data" / name).read_bytes(), name
    assert json.loads((committed / "evaluation.json").read_text()) == json.loads((worked_example.dataset / "evaluation.json").read_text())
    summary = json.loads((EXAMPLE / "summary.json").read_text())
    assert summary == worked_example.code_map.stats


def _normalise(rows):
    out = []
    for row in rows:
        norm = []
        for v in row:
            if isinstance(v, Decimal):
                v = float(v)
            if isinstance(v, float):
                v = round(v, 6) if not math.isnan(v) else v
            norm.append(v)
        out.append(tuple(norm))
    return out


@pytest.fixture(scope="module")
def postgres(worked_example, tmp_path_factory):
    pgserver = pytest.importorskip("pgserver")
    psycopg = pytest.importorskip("psycopg")
    server = pgserver.get_server(tmp_path_factory.mktemp("pg"), cleanup_mode="stop")
    try:
        server.psql(f'CREATE DATABASE "{NAME}";')
        uri = server.get_uri(NAME)
        ddl, data = worked_example.dataset / "ddl", worked_example.dataset / "data"
        # Mirrors scripts/seed/seed_wwi.py in NVIDIA/auto-ontology-eval: 01-04, COPY every CSV, then 05-06.
        with psycopg.connect(uri, autocommit=True) as conn, conn.cursor() as cur:
            for name in ["01_schemas.sql", "02_sequences.sql", "03_tables.sql", "04_indexes.sql"]:
                if (ddl / name).exists():
                    cur.execute((ddl / name).read_text())
            for csv_path in sorted(data.glob("*.csv")):
                schema, table = csv_path.stem.split(".", 1)
                with csv_path.open("r") as fh:
                    with cur.copy(f"COPY {schema.lower()}.{table.lower()} FROM STDIN WITH (FORMAT csv, HEADER true, NULL '\\N')") as copy:
                        while chunk := fh.read(65536):
                            copy.write(chunk.encode())
            for name in ["05_fkeys.sql", "06_views.sql"]:
                cur.execute((ddl / name).read_text())
        yield psycopg.connect(uri, autocommit=True)
    finally:
        server.cleanup()


@needs_clone
def test_dataset_seeds_into_postgres_and_gold_sql_matches_duckdb(worked_example, postgres):
    con = duckdb.connect(str(worked_example.duckdb), read_only=True)
    try:
        with postgres.cursor() as cur:
            for table in TABLES:
                cur.execute(f"SELECT COUNT(*) FROM {table.qualified}")
                assert cur.fetchone()[0] == len(worked_example.code_map.rows[table.name]), table.name
            cur.execute("SELECT COUNT(*) FROM information_schema.table_constraints WHERE table_schema = 'code' AND constraint_type = 'FOREIGN KEY'")
            assert cur.fetchone()[0] == sum(len(t.foreign_keys) for t in TABLES)
            for q in QUESTIONS:
                cur.execute(q["SQL"])
                assert _normalise(cur.fetchall()) == _normalise(con.execute(q["SQL"]).fetchall()), q["question_id"]
            for a in ANALYSES:
                cur.execute(a["sql"])
                assert _normalise(cur.fetchall()) == _normalise(con.execute(a["sql"]).fetchall()), a["name"]
    finally:
        con.close()


def test_gold_sql_reproduces_on_the_shipped_example():
    """The certification check passes on the committed worked example: the
    evaluation.json in the dataset folder against the DuckDB file beside it."""
    from code_ontology_bridge.governance import certification as cert

    evaluation = EXAMPLE / NAME / "evaluation.json"
    database = EXAMPLE / f"{NAME}.duckdb"
    if not (evaluation.is_file() and database.is_file()):
        pytest.skip("worked example not generated (run examples/auto-ontology/reproduce.sh)")
    out = cert.CHECKS["gold_sql_reproduces"](EXAMPLE, {"evaluation": f"{NAME}/evaluation.json", "database": f"{NAME}.duckdb"})
    assert out.passed, out.detail
    assert out.detail == f"{len(QUESTIONS)}/{len(QUESTIONS)} gold queries reproduce"

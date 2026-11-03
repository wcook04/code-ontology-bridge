"""Write the code map as a benchmark dataset folder for NVIDIA ontology-sql-eval.

Layout (what ``scripts/seed/seed_wwi.py --database-name <name>`` loads)::

    <name>/ddl/01_schemas.sql 03_tables.sql 05_fkeys.sql 06_views.sql
    <name>/data/code.<table>.csv      header row, NULL as \\N
    <name>/evaluation.json            [{question_id, db_id, question, evidence, SQL, difficulty, answer_raw, answer}]
    <name>/custom_analyses.json       [{name, description, sql}]
    <name>/snapshot.json              snapshot identity and known limits (ignored by the seeder)

The seeder applies 01-04, copies the CSVs, then applies 05-06, so tables are
created without foreign keys and the keys are added after the data is in.
Gold answers are computed by executing each gold SQL on the DuckDB file built
from the same rows.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import duckdb

from ..codemap.builder import CodeMap
from ..codemap.schema import SCHEMA, TABLES, VIEWS, alter_foreign_keys_sql, create_table_sql, create_view_sql
from .csvio import csv_name, write_table_csv


def _header(code_map: CodeMap, what: str) -> str:
    s = code_map.snapshot
    return (
        f"-- {what} for schema {SCHEMA}: code map of {s['repo_url']}\n"
        f"-- commit {s['commit_sha']}  source_fingerprint {s['source_fingerprint']}  snapshot {s['snapshot_id']}\n"
        f"-- built by {s['builder_version']} at {s['built_at']}; known limits in table {SCHEMA}.snapshot\n\n"
    )


def postgres_ddl(code_map: CodeMap) -> dict[str, str]:
    return {
        "01_schemas.sql": _header(code_map, "Schemas") + f"CREATE SCHEMA IF NOT EXISTS {SCHEMA};\n",
        "03_tables.sql": _header(code_map, "Tables (foreign keys in 05_fkeys.sql)")
        + "\n\n".join(create_table_sql(t, inline_foreign_keys=False) for t in TABLES)
        + "\n",
        "05_fkeys.sql": _header(code_map, "Foreign keys")
        + "\n".join(stmt for t in TABLES for stmt in alter_foreign_keys_sql(t))
        + "\n",
        "06_views.sql": _header(code_map, "Views")
        + "\n\n".join(f"-- {v.description}\n{create_view_sql(v)}" for v in VIEWS)
        + "\n",
    }


def jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def run_query(con: duckdb.DuckDBPyConnection, sql: str) -> list[list[Any]]:
    return [[jsonable(v) for v in row] for row in con.execute(sql).fetchall()]


def render_answer(rows: list[list[Any]]) -> str:
    if all(len(r) == 1 for r in rows):
        return ", ".join(str(r[0]) for r in rows)
    return "; ".join(", ".join(str(v) for v in r) for r in rows)


def load_json(path: str | Path | None) -> list[dict[str, Any]]:
    if not path:
        return []
    return json.loads(Path(path).read_text(encoding="utf-8"))


def export_dataset(
    code_map: CodeMap,
    out_dir: str | Path,
    *,
    duckdb_path: str | Path,
    questions: list[dict[str, Any]] = (),
    analyses: list[dict[str, Any]] = (),
    db_id: str | None = None,
) -> Path:
    out = Path(out_dir)
    (out / "ddl").mkdir(parents=True, exist_ok=True)
    (out / "data").mkdir(parents=True, exist_ok=True)
    for stale in (out / "data").glob("*.csv"):
        stale.unlink()
    for name, text in postgres_ddl(code_map).items():
        (out / "ddl" / name).write_text(text, encoding="utf-8")
    for table in TABLES:
        write_table_csv(out / "data" / csv_name(table), table, code_map.rows[table.name])

    db_id = db_id or out.name.upper()
    evaluation = []
    con = duckdb.connect(str(duckdb_path), read_only=True)
    try:
        for q in questions:
            rows = run_query(con, q["SQL"])
            evaluation.append(
                {
                    "question_id": q["question_id"],
                    "db_id": db_id,
                    "question": q["question"],
                    "evidence": q.get("evidence", ""),
                    "SQL": q["SQL"],
                    "difficulty": q.get("difficulty", ""),
                    "answer_raw": json.dumps(rows, ensure_ascii=False),
                    "answer": render_answer(rows),
                }
            )
    finally:
        con.close()
    (out / "evaluation.json").write_text(json.dumps(evaluation, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    custom = [{"name": a["name"], "description": a["description"], "sql": a["sql"]} for a in analyses]
    (out / "custom_analyses.json").write_text(json.dumps(custom, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    snapshot = dict(code_map.snapshot)
    snapshot["known_limits"] = json.loads(snapshot["known_limits"])
    (out / "snapshot.json").write_text(json.dumps(snapshot, indent=2) + "\n", encoding="utf-8")
    return out

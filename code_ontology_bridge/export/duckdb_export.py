"""Write the code map as a DuckDB file that Auto Ontology's DuckDB connector can open.

Schema ``code`` is created with PRIMARY KEY and FOREIGN KEY constraints (DuckDB
enforces both, so a load that succeeds is referentially intact) and the two
views. Rows are loaded from the same CSV files the benchmark dataset ships, so
both outputs hold identical data.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import duckdb

from ..codemap.builder import CodeMap
from ..codemap.schema import SCHEMA, TABLES, VIEWS, create_table_sql, create_view_sql
from .csvio import csv_name, write_table_csv

# Oldest DuckDB storage format to write: Auto Ontology pins duckdb>=1.5.5.
STORAGE_COMPATIBILITY = "v1.5.0"


def copy_sql(qualified_table: str, csv_path: Path) -> str:
    path = str(csv_path).replace("'", "''")
    return (
        f"COPY {qualified_table} FROM '{path}' "
        "(FORMAT csv, HEADER true, NULL '\\N', QUOTE '\"', ESCAPE '\"', ALLOW_QUOTED_NULLS false)"
    )


def ddl_statements() -> list[str]:
    statements = [f"CREATE SCHEMA IF NOT EXISTS {SCHEMA};"]
    statements += [create_table_sql(t, inline_foreign_keys=True) for t in TABLES]
    statements += [create_view_sql(v) for v in VIEWS]
    return statements


def export_duckdb(code_map: CodeMap, out_path: str | Path) -> Path:
    out = Path(out_path).resolve()
    if out.stem.lower() == SCHEMA:
        # DuckDB names the catalog after the file stem; a catalog called "code" makes
        # every `code.<table>` reference ambiguous between catalog and schema.
        raise ValueError(f"name the DuckDB file anything but {SCHEMA}.duckdb (got {out.name})")
    out.parent.mkdir(parents=True, exist_ok=True)
    for stale in (out, out.with_name(out.name + ".wal")):
        if stale.exists():
            stale.unlink()
    # Auto Ontology pins duckdb 1.5.x, which cannot read the storage format that
    # duckdb 2.x writes by default; write the older format so their connector opens it.
    con = duckdb.connect(str(out), config={"storage_compatibility_version": STORAGE_COMPATIBILITY})
    try:
        statements = ddl_statements()
        con.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA};")
        for stmt in statements[1 : 1 + len(TABLES)]:
            con.execute(stmt)
        with tempfile.TemporaryDirectory() as tmp:
            for table in TABLES:
                path = Path(tmp) / csv_name(table)
                write_table_csv(path, table, code_map.rows[table.name])
                con.execute(copy_sql(table.qualified, path))
        for stmt in statements[1 + len(TABLES) :]:
            con.execute(stmt)
        con.execute("CHECKPOINT")
    finally:
        con.close()
    return out

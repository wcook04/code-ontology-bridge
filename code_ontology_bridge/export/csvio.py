"""CSV files in the form ``COPY ... (FORMAT csv, HEADER true, NULL '\\N')`` reads.

Nulls are an unquoted ``\\N``; every non-null text value is quoted, so an empty
string, or a literal ``\\N`` in the source, can never be read back as null.
Booleans are ``true``/``false``. Postgres and DuckDB read the same bytes.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..codemap.schema import SCHEMA, Table

NULL = "\\N"


def _field(value: Any) -> str:
    if value is None:
        return NULL
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    text = str(value)
    return '"' + text.replace('"', '""') + '"'


def csv_name(table: Table) -> str:
    return f"{SCHEMA}.{table.name}.csv"


def write_table_csv(path: Path, table: Table, rows: list[dict[str, Any]]) -> None:
    names = table.column_names
    with path.open("w", encoding="utf-8", newline="") as fh:
        fh.write(",".join(names) + "\n")
        for row in rows:
            fh.write(",".join(_field(row[n]) for n in names) + "\n")

"""Write the code map's schema as an Auto Ontology model-import YAML document.

The document follows ``AutoOntologyModelDocument`` in Auto Ontology's
``auto_ontology/server/model_interchange/schemas.py`` and is meant for
``POST /api/model/import`` with ``replace=false``.

Mapping decisions (from reading their schemas.py, service.py and
dal/model_interchange.py at cdaf61e):

- Every YAML ``id`` is one of our stable ids. Their importer matches a YAML id
  against ``imported_id`` (or a live id) and stamps it on created rows, so the
  same document imports idempotently. Ids carry no commit, so a later snapshot
  of the same repository updates rather than duplicates.
- ``data_layer`` declares the eight tables and two views of schema ``code``
  with primary keys and every foreign key, which their DuckDB connector cannot
  report (its ``get_pks``/``get_fks`` return empty frames).
- ``semantic_layer.terms``: one term per entity table (file, symbol, call
  site, ...). Files and packages are rows of ``code.files``, not entity types:
  a term per file would add hundreds of instance-level terms that all
  ``represent`` the same table. Package and file descriptions stay data in
  ``code.files.description``.
- Non-key columns become column attributes of their table's term; each
  foreign-key column gets a semantic FK to the attribute of the column it
  references, mirroring their own declared-FK fast path in
  ``auto_ontology/semantic/semantic_fk.py``.
- Term and attribute descriptions are this schema's hand-written column
  documentation, never text about the analysed code.
- ``ModelTerm`` has no ``source`` field and their importer stamps
  ``source = "semantic"`` on every imported term, so the YAML cannot carry
  ``source: code_registry``; the provenance is the ``cob:`` id namespace and
  the header comment.
"""

from __future__ import annotations

import json
import re
from typing import Any

import duckdb
import yaml

from ..codemap.builder import CodeMap
from ..codemap.schema import SCHEMA, TABLES, TABLES_BY_NAME, VIEWS, Table, create_table_sql, create_view_sql

ID_PREFIX = "cob"
TERM_SOURCE = "code_registry"

TERM_NAMES = {
    "snapshot": "Code snapshot",
    "files": "Source file",
    "headings": "Docstring heading",
    "symbols": "Code symbol",
    "class_bases": "Class base",
    "calls": "Call site",
    "imports": "Import statement",
    "test_links": "Test link",
}

# Columns whose full set of distinct values is a small closed vocabulary.
ENUM_COLUMNS = {
    ("files", "description_source"),
    ("symbols", "kind"),
    ("symbols", "summary_source"),
    ("calls", "resolution"),
    ("calls", "confidence"),
    ("calls", "call_kind"),
    ("test_links", "reason"),
    ("headings", "heading"),
}

VIEW_COLUMN_DOCS = {
    "inbound_calls": "Number of resolved direct call sites whose callee is this symbol.",
    "callback_references": "Number of places where this symbol is passed by reference as an argument to another call.",
    "distinct_callers": "Number of distinct symbols that call this symbol directly or pass it as a callback.",
}
SYMBOL_COLUMN_DOCS = {c.name: c.description for c in TABLES_BY_NAME["symbols"].columns}

DUCKDB_TYPES = {"TEXT": "VARCHAR", "INTEGER": "INTEGER", "BOOLEAN": "BOOLEAN"}


class Ids:
    def __init__(self, database: str):
        self.base = f"{ID_PREFIX}:{database}"

    def database(self) -> str:
        return f"{self.base}:database"

    def schema(self) -> str:
        return f"{self.base}:schema:{SCHEMA}"

    def table(self, table: str) -> str:
        return f"{self.base}:table:{SCHEMA}.{table}"

    def column(self, table: str, column: str) -> str:
        return f"{self.base}:column:{SCHEMA}.{table}.{column}"

    def term(self, table: str) -> str:
        return f"{self.base}:term:{table}"

    def attribute(self, table: str, column: str) -> str:
        return f"{self.base}:attribute:{SCHEMA}.{table}.{column}"

    def analysis(self, name: str) -> str:
        slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
        return f"{self.base}:analysis:{slug}"


def _view_columns() -> dict[str, list[tuple[str, str]]]:
    """Column names and DuckDB types of each view, from an empty in-memory schema."""
    con = duckdb.connect()
    try:
        con.execute(f"CREATE SCHEMA {SCHEMA}")
        for t in TABLES:
            con.execute(create_table_sql(t, inline_foreign_keys=False))
        out = {}
        for v in VIEWS:
            con.execute(create_view_sql(v))
            out[v.name] = [(r[0], r[1]) for r in con.execute(f"DESCRIBE {v.qualified}").fetchall()]
        return out
    finally:
        con.close()


def _sample_values(code_map: CodeMap, table: str, column: str) -> list[Any]:
    if (table, column) not in ENUM_COLUMNS:
        return []
    return sorted({r[column] for r in code_map.rows[table] if r[column] is not None})


def _attribute_name(column: str) -> str:
    return column.replace("_", " ")


def _fk_columns(table: Table) -> dict[str, tuple[str, str]]:
    return {fk.columns[0]: (fk.ref_table, fk.ref_columns[0]) for fk in table.foreign_keys if len(fk.columns) == 1}


def build_model_document(
    code_map: CodeMap,
    *,
    database: str,
    dialect: str = "duckdb",
    analyses: list[dict[str, Any]] = (),
) -> dict[str, Any]:
    ids = Ids(database)
    type_map = DUCKDB_TYPES if dialect == "duckdb" else {k: k.lower() for k in DUCKDB_TYPES}

    tables = []
    for t in TABLES:
        tables.append(
            {
                "id": ids.table(t.name),
                "name": t.name,
                "description": t.description,
                "pk": [ids.column(t.name, c) for c in t.primary_key],
                "type": "BASE TABLE",
                "columns": [
                    {
                        "id": ids.column(t.name, c.name),
                        "name": c.name,
                        "description": c.description,
                        "type": type_map[c.sql_type],
                        "sample_values": _sample_values(code_map, t.name, c.name),
                        "is_nullable": c.nullable,
                        "is_unique": t.primary_key == (c.name,),
                    }
                    for c in t.columns
                ],
            }
        )
    for v in VIEWS:
        tables.append(
            {
                "id": ids.table(v.name),
                "name": v.name,
                "description": v.description,
                "pk": [],
                "type": "VIEW",
                "columns": [
                    {
                        "id": ids.column(v.name, name),
                        "name": name,
                        "description": VIEW_COLUMN_DOCS.get(name) or SYMBOL_COLUMN_DOCS.get(name, ""),
                        "type": col_type if dialect == "duckdb" else col_type.lower(),
                        "sample_values": [],
                        "is_nullable": True,
                        "is_unique": False,
                    }
                    for name, col_type in _view_columns()[v.name]
                ],
            }
        )

    foreign_keys = [
        {
            "source_column_id": ids.column(t.name, fk.columns[i]),
            "target_column_id": ids.column(fk.ref_table, fk.ref_columns[i]),
        }
        for t in TABLES
        for fk in t.foreign_keys
        for i in range(len(fk.columns))
    ]

    terms, semantic_fks = [], []
    for t in TABLES:
        fks = _fk_columns(t)
        attributes = [
            {
                "id": ids.attribute(t.name, c.name),
                "name": _attribute_name(c.name),
                "description": c.description,
                "column_id": ids.column(t.name, c.name),
            }
            for c in t.columns
            if c.name not in fks
        ]
        terms.append(
            {
                "id": ids.term(t.name),
                "name": TERM_NAMES[t.name],
                "description": t.description,
                "represents": [ids.table(t.name)],
                "columns_attributes": attributes,
            }
        )
        for column, (ref_table, ref_column) in fks.items():
            target = TABLES_BY_NAME[ref_table]
            if ref_column in _fk_columns(target):
                continue
            semantic_fks.append(
                {
                    "column_attribute_id": ids.attribute(ref_table, ref_column),
                    "column_id": ids.column(t.name, column),
                    "use_in_join_paths": True,
                }
            )

    custom = [
        {
            "id": ids.analysis(a["name"]),
            "name": a["name"],
            "description": a["description"],
            "sql": a["sql"],
            "sql_column_is": [],
        }
        for a in analyses
    ]

    return {
        "data_layer": {
            "databases": [
                {
                    "id": ids.database(),
                    "dialect": dialect,
                    "schemas": [
                        {"id": ids.schema(), "name": SCHEMA, "database_name": database, "tables": tables}
                    ],
                }
            ],
            "foreign_keys": foreign_keys,
            "joins": [],
        },
        "semantic_layer": {
            "terms": terms,
            "semantic_fks": semantic_fks,
            "sql_attributes": {"manual": [], "table": [], "sql": [], "bridge_table": []},
            "custom_analyses": custom,
        },
        "zones": [],
    }


def header_comment(code_map: CodeMap, database: str) -> str:
    s = code_map.snapshot
    lines = [
        "Auto Ontology model-import document for schema `code` (POST /api/model/import, replace=false).",
        f"source: {TERM_SOURCE}   id namespace: {ID_PREFIX}:{database}:",
        f"repo_url: {s['repo_url']}",
        f"commit_sha: {s['commit_sha']}",
        f"source_fingerprint: {s['source_fingerprint']}",
        f"snapshot_id: {s['snapshot_id']}",
        f"builder_version: {s['builder_version']}   built_at: {s['built_at']}",
        "known_limits:",
        *[f"  - {limit}" for limit in json.loads(s["known_limits"])],
        "Certified flags are not part of this document; they are set by PATCH from certification events.",
    ]
    return "".join(f"# {line}\n" for line in lines) + "\n"


def export_model_yaml(
    code_map: CodeMap,
    out_path,
    *,
    database: str,
    dialect: str = "duckdb",
    analyses: list[dict[str, Any]] = (),
) -> str:
    document = build_model_document(code_map, database=database, dialect=dialect, analyses=analyses)
    text = header_comment(code_map, database) + yaml.safe_dump(document, sort_keys=False, allow_unicode=True, width=100)
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return text

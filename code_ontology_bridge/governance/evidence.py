"""Evidence-carrying answers.

Auto Ontology's MCP ``ask_question`` returns a ``DataAnswer``
(``answer, sql, rows, row_count, truncated, reasoning``;
``mcp/auto_ontology_mcp/chat.py:46``). Nothing in it says which tables and
columns the SQL read, which ontology terms those belong to, or whether any of
them is certified. This module adds that, from the SQL text and the model YAML
already imported, without calling Auto Ontology.

SQL handling is a stdlib tokenizer plus heuristics, not a parser. It handles:
comments, quoted strings and identifiers, ``schema.table`` and
``db.schema.table`` names, ``FROM a, b`` lists, every ``JOIN`` form, ``AS`` and
bare aliases, ``WITH`` CTE names (not reported as tables, including
``RECURSIVE``), subqueries in ``FROM``, and ``alias.column`` references. It
does not handle: unqualified columns when more than one table is in the query
(they are reported as unattributed), ``SELECT *`` expansion, table-valued
functions, ``USING (col)`` attribution, dynamic SQL, identifiers that shadow
keywords, or scoping (an alias reused in two subqueries for different tables
resolves to the last one).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import certification as cert
from .fingerprint import file_sha256

# ---------------------------------------------------------------------------
# Tokenizer
# ---------------------------------------------------------------------------

_TOKEN_RE = re.compile(
    r"""
    (?P<ws>\s+)
  | (?P<line_comment>--[^\n]*)
  | (?P<block_comment>/\*.*?\*/)
  | (?P<string>'(?:[^']|'')*')
  | (?P<qident>"(?:[^"]|"")*"|`[^`]*`|\[[^\]]*\])
  | (?P<number>\d+(?:\.\d*)?(?:[eE][+-]?\d+)?)
  | (?P<word>[A-Za-z_][A-Za-z0-9_$]*)
  | (?P<op>::|<>|<=|>=|!=|\|\||[(),.;*=<>+\-/%])
  | (?P<other>.)
    """,
    re.VERBOSE | re.DOTALL,
)


@dataclass(frozen=True)
class Tok:
    kind: str  # word | ident | string | number | op | other
    text: str  # identifiers unquoted; words as written

    @property
    def upper(self) -> str:
        return self.text.upper() if self.kind == "word" else ""

    @property
    def is_name(self) -> bool:
        return self.kind in ("word", "ident")


def tokenize(sql: str) -> list[Tok]:
    out: list[Tok] = []
    for m in _TOKEN_RE.finditer(sql):
        kind = m.lastgroup
        text = m.group()
        if kind in ("ws", "line_comment", "block_comment"):
            continue
        if kind == "qident":
            out.append(Tok("ident", text[1:-1].replace('""', '"')))
        else:
            out.append(Tok(kind or "other", text))
    return out


KEYWORDS = {
    "SELECT", "FROM", "WHERE", "GROUP", "BY", "ORDER", "HAVING", "LIMIT", "OFFSET",
    "JOIN", "INNER", "LEFT", "RIGHT", "FULL", "OUTER", "CROSS", "NATURAL", "LATERAL",
    "ON", "USING", "AS", "WITH", "RECURSIVE", "UNION", "ALL", "DISTINCT", "INTERSECT",
    "EXCEPT", "AND", "OR", "NOT", "IN", "IS", "NULL", "LIKE", "ILIKE", "BETWEEN",
    "CASE", "WHEN", "THEN", "ELSE", "END", "EXISTS", "ASC", "DESC", "NULLS", "FIRST",
    "LAST", "TRUE", "FALSE", "OVER", "PARTITION", "WINDOW", "FILTER", "CAST",
    "INTERVAL", "QUALIFY", "VALUES", "FETCH", "NEXT", "ROWS", "ROW", "ONLY", "SEMI",
    "ANTI", "ASOF", "POSITIONAL", "TOP", "DATE", "TIMESTAMP", "TIME",
}
_CLAUSE_END = {"WHERE", "GROUP", "ORDER", "HAVING", "LIMIT", "OFFSET", "UNION", "INTERSECT",
               "EXCEPT", "WINDOW", "QUALIFY", "FETCH", "ON", "USING", "SELECT", "RETURNING"}
_JOIN_WORDS = {"JOIN"}


@dataclass
class SqlRefs:
    tables: list[str]
    aliases: dict[str, str]
    ctes: list[str]
    columns: list[tuple[str, str]]  # (table, column)
    unattributed_columns: list[str]
    notes: list[str]


def _read_name(toks: list[Tok], i: int) -> tuple[list[str], int]:
    """Read ``a.b.c`` starting at i; return parts and next index."""
    parts = [toks[i].text]
    i += 1
    while i + 1 < len(toks) and toks[i].text == "." and toks[i + 1].is_name:
        parts.append(toks[i + 1].text)
        i += 2
    return parts, i


def _skip_parens(toks: list[Tok], i: int) -> int:
    depth = 0
    while i < len(toks):
        if toks[i].text == "(":
            depth += 1
        elif toks[i].text == ")":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return i


def _qualify(parts: list[str]) -> str:
    # db.schema.table -> schema.table; schema.table and table kept as written.
    return ".".join(parts[-2:])


def extract_refs(sql: str) -> SqlRefs:
    toks = tokenize(sql)
    notes: list[str] = []
    ctes: list[str] = []

    # CTE names: WITH [RECURSIVE] name [(cols)] AS ( ... ) [, name AS (...)]*
    for i, t in enumerate(toks):
        if t.upper != "WITH":
            continue
        j = i + 1
        if j < len(toks) and toks[j].upper == "RECURSIVE":
            j += 1
        while j < len(toks) and toks[j].is_name:
            name = toks[j].text
            j += 1
            if j < len(toks) and toks[j].text == "(":
                j = _skip_parens(toks, j)
            if j < len(toks) and toks[j].upper == "AS":
                j += 1
                if j < len(toks) and toks[j].upper in ("MATERIALIZED", "NOT"):
                    j += 2 if toks[j].upper == "NOT" else 1
                ctes.append(name)
                j = _skip_parens(toks, j)
            else:
                break
            if j < len(toks) and toks[j].text == ",":
                j += 1
                continue
            break
    cte_lower = {c.lower() for c in ctes}

    tables: list[str] = []
    aliases: dict[str, str] = {}
    consumed: set[int] = set()  # token indices that are table names or aliases

    def add_table_ref(i: int) -> int:
        """Parse one table reference at i; return the index after it."""
        if i >= len(toks):
            return i
        if toks[i].text == "(":
            # Subquery or parenthesised join: its own FROMs are found by the
            # outer scan; just skip an alias after it.
            j = _skip_parens(toks, i)
            if j < len(toks) and toks[j].upper == "AS":
                j += 1
            if j < len(toks) and toks[j].is_name and toks[j].upper not in KEYWORDS:
                aliases.setdefault(toks[j].text.lower(), "(subquery)")
                j += 1
            return j
        if not toks[i].is_name or toks[i].upper in KEYWORDS - {"DATE", "TIME", "TIMESTAMP"}:
            return i + 1
        parts, j = _read_name(toks, i)
        consumed.update(range(i, j))
        if j < len(toks) and toks[j].text == "(":
            notes.append(f"table function {'.'.join(parts)}(...) not resolved")
            j = _skip_parens(toks, j)
            name = None
        else:
            name = _qualify(parts)
            if name.lower() in cte_lower:
                name_kind = "cte"
            else:
                name_kind = "table"
                if name not in tables:
                    tables.append(name)
        if j < len(toks) and toks[j].upper == "AS":
            j += 1
        if (
            j < len(toks)
            and toks[j].is_name
            and toks[j].upper not in KEYWORDS
            and not (j + 1 < len(toks) and toks[j + 1].text == ".")
        ):
            consumed.add(j)
            if name is not None:
                aliases[toks[j].text.lower()] = name if name_kind == "table" else f"(cte {name})"
            j += 1
            if j < len(toks) and toks[j].text == "(":  # alias column list
                j = _skip_parens(toks, j)
        if name is not None:
            aliases.setdefault(name.lower(), name if name_kind == "table" else f"(cte {name})")
            aliases.setdefault(name.split(".")[-1].lower(), aliases[name.lower()])
        return j

    i = 0
    while i < len(toks):
        u = toks[i].upper
        if u == "FROM" or u in _JOIN_WORDS:
            j = add_table_ref(i + 1)
            while u == "FROM" and j < len(toks) and toks[j].text == ",":
                j = add_table_ref(j + 1)
        # Visit every token, so FROMs inside skipped subqueries are seen too.
        i += 1

    # Column references.
    columns: list[tuple[str, str]] = []
    unqualified: list[str] = []
    for i, t in enumerate(toks):
        if not t.is_name or i in consumed:
            continue
        prev = toks[i - 1] if i else None
        nxt = toks[i + 1] if i + 1 < len(toks) else None
        if nxt is not None and nxt.text == "." and i + 2 < len(toks) and toks[i + 2].is_name:
            # qualifier.column (or schema.table, which the alias map skips)
            if prev is not None and prev.text == ".":
                continue
            qual = t.text.lower()
            col = toks[i + 2].text
            after = toks[i + 3] if i + 3 < len(toks) else None
            if after is not None and after.text in (".", "("):
                continue  # three-part name or function call
            target = aliases.get(qual)
            if target and not target.startswith("("):
                if (target, col) not in columns:
                    columns.append((target, col))
            elif target is None:
                notes.append(f"qualifier {t.text!r} in {t.text}.{col} is not a known alias")
            continue
        if prev is not None and prev.text == ".":
            continue
        if t.kind == "word" and t.upper in KEYWORDS:
            continue
        if nxt is not None and nxt.text == "(":
            continue  # function call
        if prev is not None and (prev.upper == "AS" or prev.upper in ("FROM", "JOIN")):
            continue
        if t.text.lower() in aliases or t.text.lower() in cte_lower:
            continue
        if t.text not in unqualified:
            unqualified.append(t.text)

    unattributed: list[str] = []
    if unqualified:
        if len(tables) == 1 and not ctes:
            for col in unqualified:
                if (tables[0], col) not in columns:
                    columns.append((tables[0], col))
        else:
            unattributed = unqualified
            notes.append("unqualified columns with several tables or CTEs are not attributed")
    if re.search(r"\bselect\s+(?:distinct\s+)?\*", sql, re.IGNORECASE) or ".*" in sql:
        notes.append("SELECT * is not expanded into columns")
    return SqlRefs(tables, aliases, ctes, columns, unattributed, notes)


# ---------------------------------------------------------------------------
# Model YAML index
# ---------------------------------------------------------------------------


@dataclass
class ModelIndex:
    table_by_id: dict[str, str]  # table id -> schema.table
    columns_by_table: dict[str, set[str]]  # schema.table (lower) -> column names (lower)
    column_by_id: dict[str, tuple[str, str]]  # column id -> (schema.table, column)
    terms: list[dict[str, Any]]


def load_model(path: Path) -> dict[str, Any]:
    import yaml  # runtime dependency of the package

    return yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}


def index_model(doc: dict[str, Any]) -> ModelIndex:
    table_by_id: dict[str, str] = {}
    columns_by_table: dict[str, set[str]] = {}
    column_by_id: dict[str, tuple[str, str]] = {}
    for db in (doc.get("data_layer") or {}).get("databases") or []:
        for schema in db.get("schemas") or []:
            for table in schema.get("tables") or []:
                qname = f"{schema.get('name', '')}.{table.get('name', '')}".strip(".")
                table_by_id[table["id"]] = qname
                cols = columns_by_table.setdefault(qname.lower(), set())
                for col in table.get("columns") or []:
                    cols.add(str(col.get("name", "")).lower())
                    column_by_id[col["id"]] = (qname, str(col.get("name", "")))
    terms = list((doc.get("semantic_layer") or {}).get("terms") or [])
    return ModelIndex(table_by_id, columns_by_table, column_by_id, terms)


def _match_table(name: str, model: ModelIndex) -> str | None:
    low = name.lower()
    if low in model.columns_by_table:
        return next(q for q in model.table_by_id.values() if q.lower() == low)
    if "." not in low:
        hits = [q for q in set(model.table_by_id.values()) if q.lower().split(".")[-1] == low]
        if len(hits) == 1:
            return hits[0]
    return None


# ---------------------------------------------------------------------------
# Snapshot
# ---------------------------------------------------------------------------


def load_snapshot(path: Path | None) -> dict[str, Any]:
    """Snapshot identity from a JSON file or from ``code.snapshot`` in DuckDB."""
    if path is None:
        return {"status": "absent", "reason": "no snapshot given"}
    path = Path(path)
    if path.suffix == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        return {"status": "loaded", "from": str(path), **data}
    try:
        import duckdb
    except ImportError:
        return {"status": "absent", "reason": "duckdb not installed"}
    con = duckdb.connect(str(path), read_only=True)
    try:
        # Catalog-qualified: a file named code.duckdb has catalog "code", and
        # then a bare code.snapshot is ambiguous between catalog and schema.
        catalog = con.execute("select current_database()").fetchone()[0]
        cur = con.execute(f'select * from "{catalog}".code.snapshot')
        names = [d[0] for d in cur.description]
        rows = cur.fetchall()
    except Exception as exc:
        return {"status": "absent", "reason": f"code.snapshot unreadable: {exc.__class__.__name__}"}
    finally:
        con.close()
    if len(rows) != 1:
        return {"status": "absent", "reason": f"code.snapshot has {len(rows)} rows, expected 1"}
    row = {k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in zip(names, rows[0])}
    return {"status": "loaded", "from": str(path), **row}


# ---------------------------------------------------------------------------
# Enrichment
# ---------------------------------------------------------------------------

DATA_ANSWER_KEYS = ("answer", "sql", "rows", "row_count", "truncated", "reasoning")


def unwrap_data_answer(raw: Any) -> dict[str, Any]:
    """Accept a bare DataAnswer or the usual MCP wrappers around one."""
    if isinstance(raw, dict):
        if "answer" in raw and "sql" in raw:
            return {k: raw.get(k) for k in DATA_ANSWER_KEYS}
        for key in ("structuredContent", "structured_content", "result", "data"):
            if key in raw:
                return unwrap_data_answer(raw[key])
        if isinstance(raw.get("content"), list):
            for part in raw["content"]:
                if isinstance(part, dict) and part.get("type") == "text":
                    try:
                        return unwrap_data_answer(json.loads(part["text"]))
                    except (json.JSONDecodeError, ValueError):
                        continue
    raise ValueError("input is not a DataAnswer (needs at least 'answer' and 'sql')")


def _unit_state(states: dict, kind: str, imported_id: str, fld: str) -> str:
    row = states.get((kind, imported_id, fld))
    return row["state"] if row else "never"


def enrich_answer(
    data_answer: Any,
    *,
    model_path: Path,
    events: list[dict[str, Any]],
    root: Path | None,
    snapshot_path: Path | None = None,
    now: str | None = None,
) -> dict[str, Any]:
    da = unwrap_data_answer(data_answer)
    refs = extract_refs(da.get("sql") or "")
    model = index_model(load_model(model_path))
    states = cert.state_index(cert.status(events, root))

    tables_used = []
    resolved_tables: dict[str, str] = {}
    for t in refs.tables:
        match = _match_table(t, model)
        resolved_tables[t] = match or t
        tables_used.append({"name": t, "model_table": match})
    columns_used = []
    for table, col in refs.columns:
        mt = resolved_tables.get(table) or _match_table(table, model)
        known = mt is not None and col.lower() in model.columns_by_table.get(mt.lower(), set())
        if mt is not None and not known:
            continue  # an identifier that is not a column of that table (e.g. a select alias)
        columns_used.append({"table": mt or table, "column": col, "in_model": known})
    used_tables = {t["model_table"].lower() for t in tables_used if t["model_table"]}
    used_cols = {(c["table"].lower(), c["column"].lower()) for c in columns_used if c["in_model"]}

    term_rows = []
    for term in model.terms:
        represents = [model.table_by_id.get(tid, tid) for tid in term.get("represents") or []]
        via_tables = [t for t in represents if t.lower() in used_tables]
        attrs = []
        for ca in term.get("columns_attributes") or []:
            col = model.column_by_id.get(ca.get("column_id", ""))
            if col and (col[0].lower(), col[1].lower()) in used_cols:
                attrs.append(
                    {
                        "imported_id": ca["id"],
                        "name": ca.get("name"),
                        "column": f"{col[0]}.{col[1]}",
                        "certification": _unit_state(states, "column_attribute", ca["id"], "certified"),
                    }
                )
        if not via_tables and not attrs:
            continue
        term_rows.append(
            {
                "imported_id": term["id"],
                "name": term.get("name"),
                "matched_via_tables": via_tables,
                "certification": {
                    "name": _unit_state(states, "term", term["id"], "name"),
                    "description": _unit_state(states, "term", term["id"], "description"),
                },
                "column_attributes": attrs,
            }
        )

    unit_states = [t["certification"]["description"] for t in term_rows]
    unit_states += [a["certification"] for t in term_rows for a in t["column_attributes"]]
    verdict = provenance_verdict(unit_states)

    return {
        "data_answer": da,
        "tables_used": tables_used,
        "columns_used": columns_used,
        "term_ids": [t["imported_id"] for t in term_rows],
        "certification_state": term_rows,
        "provenance_verdict": verdict,
        "snapshot": load_snapshot(snapshot_path),
        "model": {"path": str(model_path), "sha256": file_sha256(Path(model_path))},
        "generated_at": now or datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sql_analysis": {
            "method": "stdlib tokenizer + heuristics (code_ontology_bridge.governance.evidence)",
            "ctes": refs.ctes,
            "aliases": {k: v for k, v in refs.aliases.items() if k != v.lower()},
            "unattributed_columns": refs.unattributed_columns,
            "notes": refs.notes,
        },
        "known_limits": [
            "SQL is analysed heuristically; see sql_analysis.notes for what was not resolved",
            "a term matches when it REPRESENTS a used table or has an attribute on a used column",
            "a term counts as certified on its description flag; name certification is reported but not scored",
            "certification states come from the local event log, not from Auto Ontology's flags",
        ],
    }


def provenance_verdict(unit_states: list[str]) -> str:
    """``stale`` beats everything (a certified claim that no longer holds is
    the case a reader most needs to see); then all / some / none certified."""
    if not unit_states:
        return "uncertified"
    if "stale" in unit_states:
        return "stale"
    certified = sum(1 for s in unit_states if s == "certified")
    if certified == len(unit_states):
        return "grounded_in_certified"
    return "partially_certified" if certified else "uncertified"

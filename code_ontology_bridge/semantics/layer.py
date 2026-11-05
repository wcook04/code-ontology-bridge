"""The code semantics layer.

The base export stores what the extractor saw: one row per call site, import, base class and
definition. Questions about code are usually asked one level up: "who calls X directly",
"what can reach X", "which public functions have no docstring", "which modules depend on Y".
Each of those has a precise meaning that a SQL writer has to reconstruct from the raw rows,
and the reconstruction is where answers go wrong: a direct-caller query that forgets to drop
callback references, a reachability query that stops at a fixed depth, a "function" count that
includes classes, a directory grouping taken from the module name.

This module defines those concepts once, as DuckDB views over the base tables, and documents
each view and column in the same words in the native Auto Ontology model. The views are
derived only from the base schema and its documented semantics; nothing in them refers to a
particular repository or question. Because they are views, they stay correct when the base
rows change, and every answer computed from them can be recomputed from the base tables.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import duckdb

SCHEMA = "code"


@dataclass(frozen=True)
class LayerView:
    name: str
    description: str
    sql: str
    columns: tuple[tuple[str, str], ...]  # (column, description), in SELECT order
    key: tuple[str, ...]
    joins: tuple[tuple[str, str, str], ...] = ()  # (column, table, column) it joins to

    @property
    def qualified(self) -> str:
        return f"{SCHEMA}.{self.name}"


CALL_EDGES = LayerView(
    "call_edges",
    "One row per ordered pair of internal symbols where the first calls or references the second, "
    "aggregating every call site between them. Use calls_directly for 'calls' or 'direct callers'; "
    "a pair can exist only because the caller passes the callee as a callback (calls_directly false). "
    "Only resolved internal callees appear; calls to builtins, third-party code and unresolved names are not edges.",
    """SELECT c.caller_symbol_id,
       c.callee_symbol_id,
       count(*) FILTER (WHERE c.call_kind = 'direct') AS direct_call_sites,
       count(*) FILTER (WHERE c.call_kind = 'callback') AS callback_references,
       count(*) FILTER (WHERE c.call_kind = 'direct') > 0 AS calls_directly,
       count(*) FILTER (WHERE c.call_kind = 'callback') > 0 AS passes_as_callback,
       min(c.line) AS first_line,
       c.caller_symbol_id = c.callee_symbol_id AS is_self_call,
       min(cs.kind) AS caller_kind,
       min(cs.file_id) AS caller_file_id,
       bool_or(cf.is_test) AS caller_in_test_file,
       min(ts.kind) AS callee_kind,
       min(ts.file_id) AS callee_file_id,
       bool_or(tf.is_test) AS callee_in_test_file
FROM code.calls c
JOIN code.symbols cs ON cs.symbol_id = c.caller_symbol_id
JOIN code.files cf ON cf.file_id = cs.file_id
JOIN code.symbols ts ON ts.symbol_id = c.callee_symbol_id
JOIN code.files tf ON tf.file_id = ts.file_id
WHERE c.callee_symbol_id IS NOT NULL
GROUP BY c.caller_symbol_id, c.callee_symbol_id""",
    (
        ("caller_symbol_id", "Symbol whose body contains the call sites or callback references."),
        ("callee_symbol_id", "Internal symbol called or referenced."),
        ("direct_call_sites", "Number of call sites where the caller invokes the callee directly."),
        ("callback_references", "Number of places where the caller passes the callee as an argument, e.g. asyncio.to_thread(f)."),
        ("calls_directly", "True when the caller invokes the callee directly at least once. This is the meaning of 'X calls Y' and 'direct caller'."),
        ("passes_as_callback", "True when the caller passes the callee as a callback reference at least once."),
        ("first_line", "Smallest line number among the call sites and references in the caller's file."),
        ("is_self_call", "True when the symbol calls or references itself."),
        ("caller_kind", "function, method or class: kind of the caller (a class appears when the call is in its class body)."),
        ("caller_file_id", "File that defines the caller."),
        ("caller_in_test_file", "True when the caller is defined in a test file."),
        ("callee_kind", "function, method or class: kind of the callee. Calling a class constructs an instance."),
        ("callee_file_id", "File that defines the callee."),
        ("callee_in_test_file", "True when the callee is defined in a test file."),
    ),
    ("caller_symbol_id", "callee_symbol_id"),
    (("caller_symbol_id", "symbols", "symbol_id"), ("callee_symbol_id", "symbols", "symbol_id"),
     ("caller_file_id", "files", "file_id"), ("callee_file_id", "files", "file_id")),
)

REACHABILITY = LayerView(
    "reachability",
    "Transitive callers: one row per pair (caller, target) where a chain of call edges leads from the caller to the target, "
    "with the length of the shortest chain. direct_depth follows direct calls only and is null when the target is reachable "
    "only through a callback reference; any_depth also follows callback references. The chain length is unbounded and cycles "
    "are handled. A symbol is never listed as reaching itself. Use this view for 'directly or indirectly', 'transitively', "
    "'can reach', 'impact of changing' and shortest-depth questions instead of writing a recursive query.",
    """WITH RECURSIVE
edges AS (
  SELECT DISTINCT caller_symbol_id AS caller, callee_symbol_id AS callee, call_kind = 'direct' AS is_direct
  FROM code.calls
  WHERE callee_symbol_id IS NOT NULL AND caller_symbol_id <> callee_symbol_id),
any_r(caller, target, depth) USING KEY (caller, target) AS (
  SELECT caller, callee, 1 FROM edges
  UNION
  SELECT e.caller, r.target, r.depth + 1
  FROM any_r r JOIN edges e ON e.callee = r.caller
  LEFT JOIN recurring.any_r seen ON seen.caller = e.caller AND seen.target = r.target
  WHERE e.caller <> r.target AND (seen.caller IS NULL OR seen.depth > r.depth + 1)),
direct_r(caller, target, depth) USING KEY (caller, target) AS (
  SELECT caller, callee, 1 FROM edges WHERE is_direct
  UNION
  SELECT e.caller, r.target, r.depth + 1
  FROM direct_r r JOIN edges e ON e.callee = r.caller AND e.is_direct
  LEFT JOIN recurring.direct_r seen ON seen.caller = e.caller AND seen.target = r.target
  WHERE e.caller <> r.target AND (seen.caller IS NULL OR seen.depth > r.depth + 1))
SELECT a.caller AS caller_symbol_id,
       a.target AS target_symbol_id,
       d.depth AS direct_depth,
       a.depth AS any_depth,
       cs.kind AS caller_kind,
       cs.file_id AS caller_file_id,
       cf.is_test AS caller_in_test_file
FROM any_r a
LEFT JOIN direct_r d ON d.caller = a.caller AND d.target = a.target
JOIN code.symbols cs ON cs.symbol_id = a.caller
JOIN code.files cf ON cf.file_id = cs.file_id""",
    (
        ("caller_symbol_id", "Symbol from which a chain of calls reaches the target."),
        ("target_symbol_id", "Symbol reached."),
        ("direct_depth", "Edges in the shortest chain of direct calls from caller to target (1 = calls it directly); null when every chain needs a callback reference."),
        ("any_depth", "Edges in the shortest chain when callback references also count as edges; never larger than direct_depth."),
        ("caller_kind", "function, method or class: kind of the caller."),
        ("caller_file_id", "File that defines the caller."),
        ("caller_in_test_file", "True when the caller is defined in a test file."),
    ),
    ("caller_symbol_id", "target_symbol_id"),
    (("caller_symbol_id", "symbols", "symbol_id"), ("target_symbol_id", "symbols", "symbol_id"),
     ("caller_file_id", "files", "file_id")),
)

SYMBOL_PROFILE = LayerView(
    "symbol_profile",
    "One row per function, method and class with the facts most questions filter on: kind flags, visibility, test location, "
    "docstring presence, size, enclosing class and inbound and outbound call counts. 'Function' means kind = 'function' "
    "(module-level def); methods are defs inside a class; classes are not functions even though calling one constructs an instance.",
    """WITH inbound AS (
  SELECT callee_symbol_id AS symbol_id,
         count(DISTINCT caller_symbol_id) FILTER (WHERE calls_directly AND NOT is_self_call) AS direct_callers,
         count(DISTINCT caller_symbol_id) FILTER (WHERE NOT is_self_call) AS callers_any_kind,
         sum(direct_call_sites) AS inbound_direct_call_sites,
         sum(callback_references) AS inbound_callback_references
  FROM code.call_edges GROUP BY callee_symbol_id),
outbound AS (
  SELECT caller_symbol_id AS symbol_id,
         count(DISTINCT callee_symbol_id) FILTER (WHERE calls_directly AND NOT is_self_call) AS internal_callees
  FROM code.call_edges GROUP BY caller_symbol_id),
sites AS (
  SELECT caller_symbol_id AS symbol_id, count(*) FILTER (WHERE call_kind = 'direct') AS outgoing_call_sites
  FROM code.calls GROUP BY caller_symbol_id)
SELECT s.symbol_id, s.file_id, s.name, s.qualname, s.kind,
       s.kind = 'function' AS is_function,
       s.kind = 'method' AS is_method,
       s.kind = 'class' AS is_class,
       s.is_public,
       s.name LIKE '\\_\\_%\\_\\_' ESCAPE '\\' AS is_dunder,
       f.is_test AS in_test_file,
       f.module,
       CASE WHEN s.kind = 'method' THEN (
         SELECT min(c.symbol_id) FROM code.symbols c
         WHERE c.file_id = s.file_id AND c.kind = 'class'
           AND c.qualname = regexp_replace(s.qualname, '\\.[^.]+$', ''))
       END AS enclosing_class_symbol_id,
       s.line_start, s.line_end,
       s.line_end - s.line_start + 1 AS line_span,
       s.summary_source = 'docstring' AS has_docstring,
       coalesce(i.direct_callers, 0) AS direct_callers,
       coalesce(i.callers_any_kind, 0) AS callers_any_kind,
       coalesce(i.inbound_direct_call_sites, 0) AS inbound_direct_call_sites,
       coalesce(i.inbound_callback_references, 0) AS inbound_callback_references,
       coalesce(o.internal_callees, 0) AS internal_callees,
       coalesce(x.outgoing_call_sites, 0) AS outgoing_call_sites
FROM code.symbols s
JOIN code.files f ON f.file_id = s.file_id
LEFT JOIN inbound i ON i.symbol_id = s.symbol_id
LEFT JOIN outbound o ON o.symbol_id = s.symbol_id
LEFT JOIN sites x ON x.symbol_id = s.symbol_id""",
    (
        ("symbol_id", "Symbol ID, as in code.symbols."),
        ("file_id", "File that defines the symbol."),
        ("name", "Bare name."),
        ("qualname", "Dotted name within the module, e.g. Class.method."),
        ("kind", "function, method or class."),
        ("is_function", "True for module-level functions (kind = 'function')."),
        ("is_method", "True for functions defined in a class body."),
        ("is_class", "True for classes."),
        ("is_public", "True when neither the name nor any enclosing class name starts with an underscore."),
        ("is_dunder", "True for names of the form __name__, e.g. __init__."),
        ("in_test_file", "True when the defining file is a test file."),
        ("module", "Dotted module name of the defining file."),
        ("enclosing_class_symbol_id", "For a method, the class that defines it; null otherwise."),
        ("line_start", "First line of the definition, decorators excluded."),
        ("line_end", "Last line of the definition."),
        ("line_span", "line_end - line_start + 1."),
        ("has_docstring", "True when the symbol has a docstring (summary_source = 'docstring')."),
        ("direct_callers", "Distinct other symbols that call this one directly."),
        ("callers_any_kind", "Distinct other symbols that call it directly or pass it as a callback."),
        ("inbound_direct_call_sites", "Direct call sites, in all callers, that resolve to this symbol."),
        ("inbound_callback_references", "Places where this symbol is passed as a callback."),
        ("internal_callees", "Distinct other internal symbols this one calls directly."),
        ("outgoing_call_sites", "Direct call sites in this symbol's body, including calls to builtins and external code."),
    ),
    ("symbol_id",),
    (("symbol_id", "symbols", "symbol_id"), ("file_id", "files", "file_id"),
     ("enclosing_class_symbol_id", "symbols", "symbol_id")),
)

FILE_PROFILE = LayerView(
    "file_profile",
    "One row per Python file with its directory, top-level package, documentation, size, definition counts, "
    "internal import counts and static test links. directory is the folder that contains the file ('' at the repository root); "
    "group by directory, not by module or package, for questions about folders.",
    """WITH defs AS (
  SELECT file_id,
         count(*) FILTER (WHERE kind = 'function') AS function_count,
         count(*) FILTER (WHERE kind = 'method') AS method_count,
         count(*) FILTER (WHERE kind = 'class') AS class_count,
         count(*) FILTER (WHERE is_public) AS public_symbol_count
  FROM code.symbols GROUP BY file_id),
deps_out AS (
  SELECT file_id, count(DISTINCT imported_file_id) AS imports_internal_files
  FROM code.imports WHERE imported_file_id IS NOT NULL AND imported_file_id <> file_id GROUP BY file_id),
deps_in AS (
  SELECT imported_file_id AS file_id, count(DISTINCT file_id) AS imported_by_files
  FROM code.imports WHERE imported_file_id IS NOT NULL AND imported_file_id <> file_id GROUP BY imported_file_id),
tests AS (
  SELECT target_file_id AS file_id, count(DISTINCT test_file_id) AS linked_test_files
  FROM code.test_links GROUP BY target_file_id)
SELECT f.file_id, f.module, f.package,
       CASE WHEN strpos(f.file_id, '/') = 0 THEN '' ELSE regexp_replace(f.file_id, '/[^/]*$', '') END AS directory,
       CASE WHEN strpos(f.file_id, '/') = 0 THEN '' ELSE split_part(f.file_id, '/', 1) END AS top_directory,
       regexp_extract(f.file_id, '[^/]*$') AS file_name,
       f.is_test,
       f.file_id LIKE '%__init__.py' AS is_package_init,
       f.line_count,
       f.description_source <> 'none' AS has_module_docstring,
       coalesce(d.function_count, 0) AS function_count,
       coalesce(d.method_count, 0) AS method_count,
       coalesce(d.class_count, 0) AS class_count,
       coalesce(d.public_symbol_count, 0) AS public_symbol_count,
       coalesce(o.imports_internal_files, 0) AS imports_internal_files,
       coalesce(i.imported_by_files, 0) AS imported_by_files,
       coalesce(t.linked_test_files, 0) AS linked_test_files
FROM code.files f
LEFT JOIN defs d ON d.file_id = f.file_id
LEFT JOIN deps_out o ON o.file_id = f.file_id
LEFT JOIN deps_in i ON i.file_id = f.file_id
LEFT JOIN tests t ON t.file_id = f.file_id""",
    (
        ("file_id", "Repository-relative path."),
        ("module", "Dotted import name."),
        ("package", "Dotted package name; empty for a top-level module."),
        ("directory", "Folder containing the file, as a path without trailing slash; '' at the repository root."),
        ("top_directory", "First path component for files in a folder; '' at the repository root."),
        ("file_name", "Last path component, e.g. server.py."),
        ("is_test", "True for test files."),
        ("is_package_init", "True for __init__.py files."),
        ("line_count", "Number of lines in the file."),
        ("has_module_docstring", "True when the file has a module docstring (files.description_source is not 'none')."),
        ("function_count", "Module-level functions defined in the file."),
        ("method_count", "Methods defined in the file's classes."),
        ("class_count", "Classes defined in the file."),
        ("public_symbol_count", "Public functions, methods and classes in the file."),
        ("imports_internal_files", "Distinct other repository files this file imports."),
        ("imported_by_files", "Distinct other repository files that import this file."),
        ("linked_test_files", "Distinct test files statically linked to this file (imports or name match); not coverage."),
    ),
    ("file_id",),
    (("file_id", "files", "file_id"),),
)

FILE_DEPENDENCIES = LayerView(
    "file_dependencies",
    "Internal module dependencies: one row per ordered pair of distinct repository files where the first imports the second. "
    "Imports of external modules are excluded.",
    """SELECT i.file_id AS importer_file_id,
       i.imported_file_id,
       count(*) AS imported_names,
       min(i.line) AS first_line,
       bool_or(f.is_test) AS importer_is_test
FROM code.imports i JOIN code.files f ON f.file_id = i.file_id
WHERE i.imported_file_id IS NOT NULL AND i.imported_file_id <> i.file_id
GROUP BY i.file_id, i.imported_file_id""",
    (
        ("importer_file_id", "File containing the import statements."),
        ("imported_file_id", "Repository file it imports."),
        ("imported_names", "Import rows (one per imported name) between the two files."),
        ("first_line", "Line of the first import of that file."),
        ("importer_is_test", "True when the importing file is a test file."),
    ),
    ("importer_file_id", "imported_file_id"),
    (("importer_file_id", "files", "file_id"), ("imported_file_id", "files", "file_id")),
)

CLASS_ANCESTRY = LayerView(
    "class_ancestry",
    "Transitive inheritance among internal classes: one row per (class, ancestor) with the number of inheritance steps "
    "(1 = a direct base). Only bases that resolve to classes in the repository are followed; external bases such as "
    "Exception or BaseModel are in code.class_bases.base_name.",
    """WITH RECURSIVE anc(class_symbol_id, ancestor_symbol_id, depth) USING KEY (class_symbol_id, ancestor_symbol_id) AS (
  SELECT class_symbol_id, base_symbol_id, 1 FROM code.class_bases
  WHERE base_symbol_id IS NOT NULL AND base_symbol_id <> class_symbol_id
  UNION
  SELECT a.class_symbol_id, b.base_symbol_id, a.depth + 1
  FROM anc a JOIN code.class_bases b ON b.class_symbol_id = a.ancestor_symbol_id
  LEFT JOIN recurring.anc seen ON seen.class_symbol_id = a.class_symbol_id AND seen.ancestor_symbol_id = b.base_symbol_id
  WHERE b.base_symbol_id IS NOT NULL AND b.base_symbol_id <> a.class_symbol_id
    AND (seen.class_symbol_id IS NULL OR seen.depth > a.depth + 1))
SELECT class_symbol_id, ancestor_symbol_id, depth FROM anc""",
    (
        ("class_symbol_id", "Class."),
        ("ancestor_symbol_id", "Internal class it inherits from, directly or through other internal classes."),
        ("depth", "Inheritance steps on the shortest path; 1 for a direct base."),
    ),
    ("class_symbol_id", "ancestor_symbol_id"),
    (("class_symbol_id", "symbols", "symbol_id"), ("ancestor_symbol_id", "symbols", "symbol_id")),
)

# Order matters: symbol_profile reads call_edges.
LAYER_VIEWS: tuple[LayerView, ...] = (CALL_EDGES, REACHABILITY, SYMBOL_PROFILE, FILE_PROFILE, FILE_DEPENDENCIES, CLASS_ANCESTRY)

GLOSSARY: tuple[tuple[str, str], ...] = (
    ("calls / direct caller", "A calls B when a call site in A's body invokes B: code.call_edges with calls_directly. Passing B as an argument (a callback reference) is not a call."),
    ("callback reference", "A passes B by name as an argument to another call, e.g. asyncio.to_thread(B) or Thread(target=B): code.call_edges with passes_as_callback. The receiving call is expected to run B, but this is a static reference, not an observed execution."),
    ("reaches / transitive or indirect caller", "A chain of call edges leads from A to B: code.reachability. Use direct_depth for chains of direct calls only, any_depth when callback references count."),
    ("function, method, class", "A function is a module-level def (kind = 'function'); a method is a def in a class body; a class is neither, although calling a class constructs an instance and appears as a call to the class."),
    ("public", "is_public: neither the name nor an enclosing class name starts with an underscore. Dunder methods such as __init__ are therefore not public."),
    ("test code", "Anything defined in a file with is_test true. 'Outside tests' means in_test_file / caller_in_test_file false."),
    ("documented", "A symbol has a docstring when has_docstring is true; a file has a module docstring when has_module_docstring is true. Docstring text is in code.symbols.summary and code.files.description."),
    ("directory, package, module", "directory is the folder path of the file (code.file_profile.directory); package and module are dotted import names and differ from the folder for top-level scripts."),
    ("tested", "code.test_links records static associations (a test file imports the file or matches its name). It is not coverage; say 'linked to a test', not 'covered'."),
    ("depends on / imports", "File A depends on file B when A imports B: code.file_dependencies. External imports are in code.imports with is_internal false."),
)


def install_layer(con: duckdb.DuckDBPyConnection) -> None:
    """Create (or replace) every layer view in an open, writable DuckDB connection."""
    for view in LAYER_VIEWS:
        con.execute(f"CREATE OR REPLACE VIEW {view.qualified} AS\n{view.sql}")


def layer_context_text() -> str:
    """The layer's views, columns, keys, joins and glossary as plain text, for a prompt."""
    out = ["Code semantics layer (views over the base tables; prefer them where they fit):"]
    for v in LAYER_VIEWS:
        out.append(f"\ncode.{v.name}: {v.description} Key: {', '.join(v.key)}.")
        out.extend(f"  {name}: {desc}" for name, desc in v.columns)
        if v.joins:
            out.append("  Joins: " + "; ".join(f"{c} -> code.{t}.{tc}" for c, t, tc in v.joins))
    out.append("\nDefinitions:")
    out.extend(f"  {term}: {meaning}" for term, meaning in GLOSSARY)
    return "\n".join(out)


def extend_model_document(model: dict[str, Any], con: duckdb.DuckDBPyConnection) -> dict[str, Any]:
    """Add the layer's views, column descriptions, keys and joins to an exported native model.

    The model is the dictionary written by ``export.model_export``; the connection must hold the
    installed layer so that column types can be read back from DuckDB.
    """
    db = model["data_layer"]["databases"][0]
    schema = next(s for s in db["schemas"] if s["name"] == SCHEMA)
    base = schema["id"].rsplit(":schema:", 1)[0]
    table_id = lambda t: f"{base}:table:{SCHEMA}.{t}"  # noqa: E731
    column_id = lambda t, c: f"{base}:column:{SCHEMA}.{t}.{c}"  # noqa: E731
    views = schema.setdefault("views", [])
    existing = {v["name"] for v in views} | {t["name"] for t in schema.get("tables", [])}
    for v in LAYER_VIEWS:
        if v.name in existing:
            continue
        types = dict((r[0], r[1]) for r in con.execute(f"DESCRIBE {v.qualified}").fetchall())
        views.append({
            "id": table_id(v.name), "name": v.name, "description": v.description,
            "pk": [column_id(v.name, c) for c in v.key], "type": "VIEW",
            "columns": [{"id": column_id(v.name, c), "name": c, "description": d, "type": types[c],
                         "sample_values": [], "is_nullable": True, "is_unique": v.key == (c,)}
                        for c, d in v.columns],
        })
    fks = db.setdefault("foreign_keys", [])
    for v in LAYER_VIEWS:
        for c, t, tc in v.joins:
            fks.append({"source_column_id": column_id(v.name, c), "target_column_id": column_id(t, tc)})
    return model

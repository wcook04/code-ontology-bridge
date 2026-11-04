"""The relational model of schema ``code``: one definition, rendered for each target.

Every exporter reads these definitions, so the DuckDB file, the Postgres DDL of
the benchmark dataset and the model-import YAML cannot drift apart. Column
descriptions are written here by hand as documentation of this schema; they
describe the columns, never the analysed code.
"""

from __future__ import annotations

from dataclasses import dataclass, field

SCHEMA = "code"


@dataclass(frozen=True)
class Column:
    name: str
    sql_type: str  # Postgres type name that DuckDB also accepts
    nullable: bool
    description: str
    allowed: tuple[str, ...] = ()  # closed vocabulary, enforced by a CHECK constraint


@dataclass(frozen=True)
class ForeignKey:
    columns: tuple[str, ...]
    ref_table: str
    ref_columns: tuple[str, ...]


@dataclass(frozen=True)
class Table:
    name: str
    description: str
    columns: tuple[Column, ...]
    primary_key: tuple[str, ...]
    foreign_keys: tuple[ForeignKey, ...] = field(default_factory=tuple)

    @property
    def column_names(self) -> list[str]:
        return [c.name for c in self.columns]

    @property
    def qualified(self) -> str:
        return f"{SCHEMA}.{self.name}"


def _c(name: str, sql_type: str, description: str, *, nullable: bool = False, allowed: tuple[str, ...] = ()) -> Column:
    return Column(name, sql_type, nullable, description, allowed)


RESOLUTIONS = ("same_file", "imported", "method_on_self", "builtin", "external", "dynamic_attribute", "unresolved")
INTERNAL_RESOLUTIONS = RESOLUTIONS[:3]
CALL_KINDS = ("direct", "callback")


SNAPSHOT = Table(
    "snapshot",
    "One row identifying the analysed source: repository, commit, content fingerprint, builder and its known limits.",
    (
        _c("snapshot_id", "TEXT", "Stable id of this snapshot: commit prefix and fingerprint prefix."),
        _c("repo_url", "TEXT", "URL of the analysed repository."),
        _c("commit_sha", "TEXT", "Commit SHA of the analysed checkout.", nullable=True),
        _c("built_at", "TEXT", "UTC time the map was built, ISO 8601 (SOURCE_DATE_EPOCH when set)."),
        _c("builder_version", "TEXT", "Name and version of the builder that produced the rows."),
        _c("source_fingerprint", "TEXT", "16-hex SHA-256 digest over sorted 'path NUL file-sha256' lines of every analysed file."),
        _c("file_count", "INTEGER", "Number of Python files analysed."),
        _c("omitted_file_count", "INTEGER", "Number of Python files found but not analysed (excluded or unparseable)."),
        _c("known_limits", "TEXT", "JSON array of plain-language limits of the static analysis."),
    ),
    ("snapshot_id",),
)

FILES = Table(
    "files",
    "One row per analysed Python source file. Module and package descriptions are in files.description; a package description belongs to its __init__.py row.",
    (
        _c("file_id", "TEXT", "Repository-relative path of the file, with forward slashes."),
        _c("package", "TEXT", "Dotted name of the package that contains the module; empty for a top-level module."),
        _c("module", "TEXT", "Dotted import name of the module (a package's __init__.py has the package's name)."),
        _c("is_test", "BOOLEAN", "True when the path or file name marks the file as a test (tests/ or test/ directory, test_*.py, *_test.py, conftest.py)."),
        _c("line_count", "INTEGER", "Number of lines in the file."),
        _c("sha256", "TEXT", "SHA-256 of the file's bytes; used to detect stale certifications."),
        _c("description", "TEXT", "Verbatim description from the module docstring; empty when the file has none."),
        _c("description_source", "TEXT", "Where the description came from: heading_purpose, module_docstring or none.", allowed=("heading_purpose", "module_docstring", "none")),
        _c("has_fixed_headings", "BOOLEAN", "True when the module docstring uses the fixed headings [PURPOSE], [INTERFACE], [FLOW], [DEPENDENCIES] or [CONSTRAINTS]."),
    ),
    ("file_id",),
)

HEADINGS = Table(
    "headings",
    "Optional fixed sections and contract atoms from module docstrings only. This table can be empty even when ordinary module and function docstrings exist. Function docstrings are in symbols.summary, not this table.",
    (
        _c("file_id", "TEXT", "File whose module docstring holds the heading."),
        _c("heading", "TEXT", "Heading name such as [PURPOSE], or an atom name such as Teleology or Fails."),
        _c("value", "TEXT", "Verbatim text under the heading or after the atom."),
        _c("ordinal", "INTEGER", "Position of the heading within the file's docstring, from 1."),
    ),
    ("file_id", "ordinal"),
    (ForeignKey(("file_id",), "files", ("file_id",)),),
)

SYMBOLS = Table(
    "symbols",
    "Functions, methods and classes, their definition locations and extracted docstring summaries. Use this table for function definitions and function docstring questions.",
    (
        _c("symbol_id", "TEXT", "Stable id: file path, '::', qualified name."),
        _c("file_id", "TEXT", "File that defines the symbol."),
        _c("name", "TEXT", "Bare name of the symbol."),
        _c("qualname", "TEXT", "Dotted name within the module, e.g. Class.method."),
        _c("kind", "TEXT", "function, method or class.", allowed=("function", "method", "class")),
        _c("line_start", "INTEGER", "First line of the definition, decorators excluded."),
        _c("line_end", "INTEGER", "Last line of the definition."),
        _c("is_public", "BOOLEAN", "True when neither the name nor any enclosing class name starts with an underscore."),
        _c("summary", "TEXT", "First paragraph (or Teleology atom) of this function, method or class docstring, with whitespace normalized; empty when absent. This is the function documentation, unlike optional module headings."),
        _c("summary_source", "TEXT", "docstring or none.", allowed=("docstring", "none")),
    ),
    ("symbol_id",),
    (ForeignKey(("file_id",), "files", ("file_id",)),),
)

CLASS_BASES = Table(
    "class_bases",
    "Base classes named in each class statement, in order, with the internal class each one resolves to.",
    (
        _c("class_symbol_id", "TEXT", "Class whose statement names the base."),
        _c("ordinal", "INTEGER", "Position of the base in the class statement, from 1."),
        _c("base_name", "TEXT", "Base expression as written, e.g. SQLDatabase, base.SQLDatabase or Generic[T]."),
        _c(
            "base_symbol_id",
            "TEXT",
            "Internal class the base resolves to by the same static rules as calls; null for external, builtin or unresolvable bases.",
            nullable=True,
        ),
    ),
    ("class_symbol_id", "ordinal"),
    (
        ForeignKey(("class_symbol_id",), "symbols", ("symbol_id",)),
        ForeignKey(("base_symbol_id",), "symbols", ("symbol_id",)),
    ),
)

CALLS = Table(
    "calls",
    "Call edges inside functions, methods and class bodies, with how the callee was resolved. "
    "Direct call sites are all kept; those without an internal callee have a null callee and are classified as builtin, external, dynamic_attribute or unresolved. "
    "Callback rows record an internal function or method passed by reference as an argument to another call, e.g. asyncio.to_thread(f, x).",
    (
        _c("call_id", "TEXT", "Stable id: file path, line, column and a sequence number (for a callback row, the position of the argument)."),
        _c("caller_symbol_id", "TEXT", "Symbol whose body contains the call."),
        _c("callee_symbol_id", "TEXT", "Internal callee symbol; set only for same_file, imported and method_on_self, null otherwise.", nullable=True),
        _c("callee_name", "TEXT", "Callee as written at the call site, e.g. self.save or pd.read_csv; for a callback row, the reference as written in the argument."),
        _c("line", "INTEGER", "Line of the call."),
        _c(
            "resolution",
            "TEXT",
            "same_file, imported or method_on_self (internal callee found); builtin (a Python builtin such as len); "
            "external (rooted in a third-party or standard-library import, or a module-level name assigned from one, e.g. logger); "
            "dynamic_attribute (a method on an object whose type is not statically known, e.g. row.get); unresolved (anything else).",
            allowed=RESOLUTIONS,
        ),
        _c("confidence", "TEXT", "high or low: low for inherited methods, callback rows, dynamic_attribute and unresolved.", allowed=("high", "low")),
        _c(
            "call_kind",
            "TEXT",
            "direct (the call site invokes the callee) or callback (an internal function or method passed as an argument, "
            "e.g. asyncio.to_thread(f, x), executor.submit(f) or Thread(target=f), which the receiving call is expected to invoke). "
            "Callback rows always carry a callee and low confidence.",
            allowed=CALL_KINDS,
        ),
    ),
    ("call_id",),
    (
        ForeignKey(("caller_symbol_id",), "symbols", ("symbol_id",)),
        ForeignKey(("callee_symbol_id",), "symbols", ("symbol_id",)),
    ),
)

IMPORTS = Table(
    "imports",
    "Import statements, one row per imported name, with the internal file each resolves to.",
    (
        _c("import_id", "TEXT", "Stable id: file path, line and a sequence number."),
        _c("file_id", "TEXT", "File containing the import."),
        _c("imported_file_id", "TEXT", "Internal file the import resolves to; null for external or unresolvable imports.", nullable=True),
        _c("module_name", "TEXT", "Absolute dotted module name imported (relative imports resolved)."),
        _c("line", "INTEGER", "Line of the import statement."),
        _c("is_internal", "BOOLEAN", "True when the module belongs to the analysed repository."),
    ),
    ("import_id",),
    (
        ForeignKey(("file_id",), "files", ("file_id",)),
        ForeignKey(("imported_file_id",), "files", ("file_id",)),
    ),
)

TEST_LINKS = Table(
    "test_links",
    "Static links from test files to the source files they exercise.",
    (
        _c("test_file_id", "TEXT", "Test file."),
        _c("target_file_id", "TEXT", "Non-test file the test is linked to."),
        _c("reason", "TEXT", "imports_target (the test imports the file) or name_match (test_<name>.py matches <name>.py).", allowed=("imports_target", "name_match")),
    ),
    ("test_file_id", "target_file_id", "reason"),
    (
        ForeignKey(("test_file_id",), "files", ("file_id",)),
        ForeignKey(("target_file_id",), "files", ("file_id",)),
    ),
)

# Load order respects foreign keys.
TABLES: tuple[Table, ...] = (SNAPSHOT, FILES, HEADINGS, SYMBOLS, CLASS_BASES, CALLS, IMPORTS, TEST_LINKS)
TABLES_BY_NAME = {t.name: t for t in TABLES}


@dataclass(frozen=True)
class View:
    name: str
    description: str
    sql: str  # body after AS, Postgres dialect that DuckDB also accepts

    @property
    def qualified(self) -> str:
        return f"{SCHEMA}.{self.name}"


VIEWS: tuple[View, ...] = (
    View(
        "inbound_call_counts",
        "Every symbol with the number of resolved direct call sites that target it, the number of callback references to it, and the number of distinct callers of either kind.",
        """SELECT s.symbol_id, s.file_id, s.name, s.qualname, s.kind, s.is_public,
       SUM(CASE WHEN c.call_kind = 'direct' THEN 1 ELSE 0 END) AS inbound_calls,
       SUM(CASE WHEN c.call_kind = 'callback' THEN 1 ELSE 0 END) AS callback_references,
       COUNT(DISTINCT c.caller_symbol_id) AS distinct_callers
FROM code.symbols s
LEFT JOIN code.calls c ON c.callee_symbol_id = s.symbol_id
GROUP BY s.symbol_id, s.file_id, s.name, s.qualname, s.kind, s.is_public""",
    ),
    View(
        "untested_public_symbols",
        "Public symbols in non-test files whose file no test file links to.",
        """SELECT s.symbol_id, s.file_id, s.name, s.qualname, s.kind
FROM code.symbols s
JOIN code.files f ON f.file_id = s.file_id
WHERE s.is_public
  AND NOT f.is_test
  AND NOT EXISTS (SELECT 1 FROM code.test_links t WHERE t.target_file_id = s.file_id)""",
    ),
)


def create_table_sql(table: Table, *, inline_foreign_keys: bool) -> str:
    """CREATE TABLE statement; foreign keys inline (DuckDB) or left for ALTER TABLE (Postgres)."""
    lines = []
    for col in table.columns:
        null = "" if col.nullable else " NOT NULL"
        check = ""
        if col.allowed:
            check = f" CHECK ({col.name} IN (" + ", ".join(f"'{v}'" for v in col.allowed) + "))"
        lines.append(f"    {col.name} {col.sql_type}{null}{check}")
    lines.append(f"    PRIMARY KEY ({', '.join(table.primary_key)})")
    if inline_foreign_keys:
        for fk in table.foreign_keys:
            lines.append(
                f"    FOREIGN KEY ({', '.join(fk.columns)}) REFERENCES {SCHEMA}.{fk.ref_table} ({', '.join(fk.ref_columns)})"
            )
    return f"CREATE TABLE {table.qualified} (\n" + ",\n".join(lines) + "\n);"


def foreign_key_name(table: Table, fk: ForeignKey) -> str:
    return f"fk_{table.name}_{'_'.join(fk.columns)}"


def alter_foreign_keys_sql(table: Table) -> list[str]:
    return [
        f"ALTER TABLE {table.qualified} ADD CONSTRAINT {foreign_key_name(table, fk)} "
        f"FOREIGN KEY ({', '.join(fk.columns)}) REFERENCES {SCHEMA}.{fk.ref_table} ({', '.join(fk.ref_columns)});"
        for fk in table.foreign_keys
    ]


def create_view_sql(view: View) -> str:
    return f"CREATE OR REPLACE VIEW {view.qualified} AS\n{view.sql};"

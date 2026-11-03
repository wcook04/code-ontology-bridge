-- Tables (foreign keys in 05_fkeys.sql) for schema code: code map of https://github.com/NVIDIA/auto-ontology
-- commit cdaf61e1bd0cf3820d11d72b43bb460816aebbd3  source_fingerprint 158fe223627725d6  snapshot cdaf61e1bd0c-158fe2236277
-- built by code-ontology-bridge 0.1.0 at 2026-11-03T08:41:39Z; known limits in table code.snapshot

CREATE TABLE code.snapshot (
    snapshot_id TEXT NOT NULL,
    repo_url TEXT NOT NULL,
    commit_sha TEXT,
    built_at TEXT NOT NULL,
    builder_version TEXT NOT NULL,
    source_fingerprint TEXT NOT NULL,
    file_count INTEGER NOT NULL,
    omitted_file_count INTEGER NOT NULL,
    known_limits TEXT NOT NULL,
    PRIMARY KEY (snapshot_id)
);

CREATE TABLE code.files (
    file_id TEXT NOT NULL,
    package TEXT NOT NULL,
    module TEXT NOT NULL,
    is_test BOOLEAN NOT NULL,
    line_count INTEGER NOT NULL,
    sha256 TEXT NOT NULL,
    description TEXT NOT NULL,
    description_source TEXT NOT NULL CHECK (description_source IN ('heading_purpose', 'module_docstring', 'none')),
    has_fixed_headings BOOLEAN NOT NULL,
    PRIMARY KEY (file_id)
);

CREATE TABLE code.headings (
    file_id TEXT NOT NULL,
    heading TEXT NOT NULL,
    value TEXT NOT NULL,
    ordinal INTEGER NOT NULL,
    PRIMARY KEY (file_id, ordinal)
);

CREATE TABLE code.symbols (
    symbol_id TEXT NOT NULL,
    file_id TEXT NOT NULL,
    name TEXT NOT NULL,
    qualname TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('function', 'method', 'class')),
    line_start INTEGER NOT NULL,
    line_end INTEGER NOT NULL,
    is_public BOOLEAN NOT NULL,
    summary TEXT NOT NULL,
    summary_source TEXT NOT NULL CHECK (summary_source IN ('docstring', 'none')),
    PRIMARY KEY (symbol_id)
);

CREATE TABLE code.class_bases (
    class_symbol_id TEXT NOT NULL,
    ordinal INTEGER NOT NULL,
    base_name TEXT NOT NULL,
    base_symbol_id TEXT,
    PRIMARY KEY (class_symbol_id, ordinal)
);

CREATE TABLE code.calls (
    call_id TEXT NOT NULL,
    caller_symbol_id TEXT NOT NULL,
    callee_symbol_id TEXT,
    callee_name TEXT NOT NULL,
    line INTEGER NOT NULL,
    resolution TEXT NOT NULL CHECK (resolution IN ('same_file', 'imported', 'method_on_self', 'builtin', 'external', 'dynamic_attribute', 'unresolved')),
    confidence TEXT NOT NULL CHECK (confidence IN ('high', 'low')),
    call_kind TEXT NOT NULL CHECK (call_kind IN ('direct', 'callback')),
    PRIMARY KEY (call_id)
);

CREATE TABLE code.imports (
    import_id TEXT NOT NULL,
    file_id TEXT NOT NULL,
    imported_file_id TEXT,
    module_name TEXT NOT NULL,
    line INTEGER NOT NULL,
    is_internal BOOLEAN NOT NULL,
    PRIMARY KEY (import_id)
);

CREATE TABLE code.test_links (
    test_file_id TEXT NOT NULL,
    target_file_id TEXT NOT NULL,
    reason TEXT NOT NULL CHECK (reason IN ('imports_target', 'name_match')),
    PRIMARY KEY (test_file_id, target_file_id, reason)
);

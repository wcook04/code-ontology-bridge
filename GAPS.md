# Gap tracker

One row per Auto Ontology capability where this repository adds something, checked against Auto Ontology's code at upstream `cdaf61e` (3 Nov 2026). Nothing here requires a change to Auto Ontology.

Status values:
- **checked against their code**: a test loads Auto Ontology's own source or files and runs our output through it;
- **tested here**: our component has tests, and its link to Auto Ontology is by code reading at the cited lines;
- **code reading**: a statement about Auto Ontology's behaviour, not executed;
- **later**: planned.

No row has been run against a live Auto Ontology server; that needs Docker and an NVIDIA API key.

| # | Capability | What Auto Ontology's code does today | What this repository adds | Plugs in through | Status | Evidence |
|---|---|---|---|---|---|---|
| G1 | Discover an ontology from sources | Sources are relational engines: a connector implements `SQLDatabase` (`auto_ontology/connectors/base.py:99`) | a code map as eight tables: files, headings, symbols, class bases, calls (direct and callback), imports, test links, snapshot | `CONNECTION_STRINGS=duckdb:///…/auto_ontology_code.duckdb` (their reference connector) | checked against their code | their `DuckDBDatabase`, loaded from their source, runs `get_tables`, `get_columns`, `get_views` and `execute` on our file (`tests/export`) |
| G2 | Joins | Declared foreign keys are used as given, and the LLM suggests keys only for undeclared columns (`semantic/fk_suggester.py:117-126`). The DuckDB connector reports no keys (`connectors/duckdb.py:215-219`), so for a DuckDB source every key goes to the suggestion path | keys declared in the dataset DDL and in the model YAML | dataset `ddl/05_fkeys.sql`; `POST /api/model/import` | checked against their code | YAML validates against their `AutoOntologyModelDocument` and round-trips unchanged; keys enforced in DuckDB and PostgreSQL |
| G3 | Validate queries against certified definitions | The text-to-SQL validators do not read the certified flags (`grep -rn certif auto_ontology/retrieval` finds one comment) | certification checks whose results decide the flags | existing PATCH routes | tested here | `tests/governance`; planned paths checked against their OpenAPI file |
| G4 | Certification record | Certified booleans plus `modified` and `modified_by` (`dal/schema.py:131-153`); their skill notes the fields "are not an atomic review/promotion system" (`skills/nvidia-ontology-management/references/publication.md:98`) | an append-only history per certification: check, actor, source fingerprint, commit, rollback target, stale detection | sidecar log; PATCH planner (dry run by default) | tested here | `tests/governance` |
| G5 | Provenance with answers | `DataAnswer` carries answer, sql, rows, row_count, truncated and reasoning (`mcp/auto_ontology_mcp/chat.py:46`) | the tables, columns and terms used, their certification state, and the snapshot | wraps the MCP `ask_question` result | tested here | `tests/governance`; SQL parsing is heuristic (`docs/governance.md`) |
| G6 | Reconcile definitions | A term name already owned by another table is qualified as `name (db.schema.table)`, as its docstring documents (`dal/terms.py:417`) | resolution in a fixed order with a stated reason per decision, and explicit ambiguity | before model import | tested here | worked examples: two "revenue" definitions; two `utils` modules |
| G7 | Fold corrections back | Corrections are PATCH edits | certification events as the correction record; stale checks reopen them | sidecar log | later | |
| G8 | Benchmarks | Datasets in `NVIDIA/auto-ontology-eval` (GitHub redirects `ontology-sql-eval` there) are relational | a code-question set with reference SQL and named analyses, in their dataset layout | their seed script (`scripts/seed/seed_wwi.py --database-name`) and benchmark | checked against their code | folder loaded into PostgreSQL in their seed order; DuckDB and PostgreSQL return the same rows for every reference query |
| G9 | Identity through import | Import keeps the YAML id as `imported_id` and assigns a new UUID; `imported_id` is not in any response (0 occurrences in `docs/openapi/auto-ontology-api.json`) | an id map input for certification requests; a possible request: return `imported_id` in responses | `--id-map` | code reading | |
| G10 | Connect a source and import its model | `catalog_database.name` is unique (`dal/schema.py:183`) and import inserts without conflict handling (`dal/model_interchange.py:830-840`), so importing a model of an already connected database fails | import the YAML onto a store where that database is not yet connected; the YAML creates its own catalog rows | `POST /api/model/import` | code reading | |
| G11 | Term origin | Imported terms are stamped `source = "semantic"`; `ModelTerm` has no `source` field (`server/model_interchange/schemas.py:107-112`) | origin carried in the `cob:<db>:` id namespace | `imported_id` | code reading | |

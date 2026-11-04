# code-ontology-bridge: build spec

This specification describes the source tables, exports and local governance commands. The worked example maps Auto Ontology's own repository. Start with the [README](README.md) for the purpose and [GAPS.md](GAPS.md) for implementation limits. The data interfaces are unchanged upstream; the recorded public-model question run also uses a compatibility patch.

Hard rules
- The data exports use existing Auto Ontology interfaces named below. Successful question answering is a separate integration step with its own model configuration and patch.
- Nothing is invented. Every description carries `description_source`. If a file has no docstring, its description is empty and the source is `none`. No LLM-written descriptions in this repo.
- Every artifact carries the snapshot identity (repo URL, commit SHA, source fingerprint, builder version) and a `known_limits` list.
- Python 3.12, stdlib `ast` for analysis. Runtime deps: `duckdb`, `pyyaml`. Dev deps: `pytest`, `pydantic` (to validate against their schema). Managed with `uv`.
- Package `code_ontology_bridge`, CLI entry point `cob`.

## Entry points in Auto Ontology (verified at upstream cdaf61e)

1. `CONNECTION_STRINGS=duckdb:///abs/path/code.duckdb`. DuckDB is their reference `SQLDatabase` connector (`auto_ontology/connectors/duckdb.py`). Its `get_pks`/`get_fks` return empty frames, so their LLM guesses joins; we therefore also ship (2) and (3) which declare keys.
2. Benchmark dataset folder for `NVIDIA/auto-ontology-eval` (`datasets/<name>/`): `ddl/01_schemas.sql 03_tables.sql 05_fkeys.sql 06_views.sql`, `data/<schema>.<table>.csv` (header row, NULL as `\N`), `evaluation.json` (list of `{question_id, db_id, question, evidence, SQL, difficulty, answer_raw, answer}`), `custom_analyses.json` (list of `{name, description, sql}`). Their `scripts/seed/seed_wwi.py --database-name <name>` loads any such folder into Postgres; their benchmark then compares a schema-only arm with the ontology-grounded arm by deterministic execution match.
3. Model import YAML, `POST /api/model/import` (`auto_ontology/server/model_interchange/schemas.py`, pydantic-only). Use `imported_id` for our stable ids and import with `replace=false`. Their `ModelTerm` has no `source` field (`schemas.py:107-112`), so the source cannot travel in the YAML. Live ids differ from `imported_id` after import and no route returns `imported_id`, so PATCH planning takes an id map. Never name the DuckDB file `code.duckdb`: its catalog would clash with schema `code`. The YAML cannot carry certified flags; those are set by PATCH (see governance).

## Relational model (schema `code`, Postgres dialect that DuckDB also accepts)

- `code.snapshot(snapshot_id PK, repo_url, commit_sha, built_at, builder_version, source_fingerprint, file_count, omitted_file_count, known_limits)` one row.
- `code.files(file_id PK = repo-relative path, package, module, is_test, line_count, sha256, description, description_source in {heading_purpose, module_docstring, none}, has_fixed_headings)`.
- `code.headings(file_id FK, heading, value, ordinal)` fixed headings when present: `[PURPOSE]`, `[INTERFACE]`, `[FLOW]`, `[DEPENDENCIES]`, `[CONSTRAINTS]`, and atoms `Teleology:`, `Mechanism:`, `Guarantee:`, `Fails:`, `Reads:`, `Writes:`.
- `code.symbols(symbol_id PK = path::qualname, file_id FK, name, qualname, kind in {function, method, class}, line_start, line_end, is_public, summary, summary_source in {docstring, none})`.
- `code.calls(call_id PK, caller_symbol_id FK, callee_symbol_id FK nullable, callee_name, line, resolution in {same_file, imported, method_on_self, builtin, external, dynamic_attribute, unresolved}, confidence in {high, low})`. Only the first three carry a callee; every other call is kept with a null callee so nothing is silently dropped or guessed.
  Each call also has `call_kind in {direct, callback}`: a callback row is an internal function passed as a call argument (for example to `asyncio.to_thread`), always with a callee and low confidence.
- `code.class_bases(class_symbol_id FK, ordinal, base_name, base_symbol_id FK nullable)`.
- `code.imports(import_id PK, file_id FK, imported_file_id FK nullable, module_name, line, is_internal)`.
- `code.test_links(test_file_id FK, target_file_id FK, reason in {imports_target, name_match})`.
- Views: `code.inbound_call_counts`, `code.untested_public_symbols`.

## Governance layer (sidecars, JSONL/JSON)

- Certification events: `{event_id, target_kind, target_imported_id, field, decision in {certify, revoke}, actor, check_id, check_result, source_fingerprint, commit_sha, at, rollback_to_event_id}`. Flags are set on Auto Ontology only from events whose check passed, via the existing PATCH routes. A certification is stale when the stored fingerprint no longer matches the file.
- Evidence-carrying answer: wraps their MCP `DataAnswer` (`answer, sql, rows, row_count, truncated, reasoning`) with `{tables_used, columns_used, term_ids, certification_state, snapshot, model, generated_at}` parsed from the SQL with sqlglot-free stdlib heuristics or `sqlglot` if added.
- Reconciliation: input = several definitions of one term from different sources; fixed order: canonical id, canonical name, declared resolution with a reason, unique alias, else return `ambiguous` with all candidates. Never rename silently.

## Tracking

`GAPS.md` keeps one row per Auto Ontology gap: their claim, what the code does (file:line at a pinned SHA), our component, status, evidence.

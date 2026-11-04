# Governance commands

These local commands record checks, plan certification updates, annotate returned SQL and reconcile definitions. They do not enforce certified-only retrieval in Auto Ontology. A check establishes only the property it tests; the live flag demonstration used reference-query reproduction, which does not validate the truth of the term text being flagged.

Known defects and unverified integrations are tracked in [GAPS.md](../GAPS.md). In particular, revoking the sole column-attribute certification currently loses the parent term ID needed to send its update. Stale or failed local state withholds an update by default; it does not clear a server flag without `--unset-stale`.

## Components

Three sidecar components in `code_ontology_bridge/governance/`, each filling a gap that Auto Ontology's own code or documentation names. None of them needs a change to Auto Ontology: they read the model YAML you already imported, the MCP answer you already received, and they talk to Auto Ontology only through PATCH routes it already exposes. All citations are to upstream `NVIDIA/auto-ontology` at `cdaf61e`.

Commands (mounted on `cob` through `governance/cli.py:register`):

| Command | Does |
|---|---|
| `cob certify --log L --targets T --root R --actor A` | runs each target's check, appends one event per target |
| `cob certify --log L --revoke EVENT_ID --reason "..." --actor A` | appends a revoke that rolls that event back |
| `cob cert-status --log L --root R [--plan-patches --id-map M] [--apply --base-url U]` | recomputes state; plans or sends PATCH requests |
| `cob enrich-answer --answer A.json --model model.yaml --log L --snapshot code.duckdb` | wraps an MCP `DataAnswer` with evidence |
| `cob reconcile --definitions D.json --resolutions R.json` | resolves several definitions of a term in a fixed order |

## 1. Certification history

Theirs: "Current Auto Ontology certification fields are not an atomic review/promotion system." (`skills/nvidia-ontology-management/references/publication.md:98`)

The fields are booleans: `term.name_certified` and `term.description_certified` (`auto_ontology/dal/schema.py:464-465`), `column_attribute.certified` (`:502`), `sql_attribute.certified` (`:607`). Each of those rows also carries `created`, `modified`, `created_by` and `modified_by` (`_edited()`, `dal/schema.py:131-153`, used at `:467`, `:511`, `:617`), and the PATCH routes fill `modified_by` with the requesting user (`server/terms/router.py:234`, `server/sql_attributes/router.py:224`). So the row keeps its last editor and edit time, shared by every field of that row; there is no per-certification history, reason, evidence or earlier value. The log below adds that history alongside their flags.

**What ours does** (`certification.py`)

- An append-only JSONL log. Each event has the SPEC keys `event_id, target_kind, target_imported_id, field, decision, actor, check_id, check_result, source_fingerprint, commit_sha, at, rollback_to_event_id`, plus `source_paths`, `check_detail`, `check_params` and `parent_term_imported_id`. Lines are never rewritten. A failed check is recorded too, and it displaces an earlier pass because the current text did not pass.
- Checks are plain functions registered with `@register_check(id)`; `--checks-module` imports more. Two ship:
  - `docstring_matches_description`: re-parses the file with `ast` and passes only when the certified description is verbatim text from the current module or symbol docstring (whitespace normalised). An empty description never passes.
  - `gold_sql_reproduces`: runs every gold `SQL` in an ontology-sql-eval `evaluation.json` against the DuckDB file and compares rows with the recorded rows in `answer_raw` (JSON; `answer` is used only when `answer_raw` is missing or not JSON), as a multiset with floats to 6 places. A test runs it on the shipped worked example.
- `cert-status` recomputes state from the events and the files as they are now. The `source_fingerprint` is the first 16 hex characters of a SHA-256 over sorted `path NUL sha256(content)` lines for the files the check read, so a stale certification is detected by content, never by modification time. States: `certified`, `stale` (fingerprint moved, or no `--root` given so freshness is unchecked), `failed`, `revoked`, `never`.
- Rollback is a revoke event whose `rollback_to_event_id` names the target's current effective event. State falls back to whatever was effective before it: revoking a bad re-certification restores the earlier one (still subject to freshness); revoking the only certification leaves the target `revoked`.

**How it plugs in.** The planner emits requests for the existing routes (all mounted under `/api` at `auto_ontology/server/__main__.py:102,110`):

| Target | Route | Body (their model) |
|---|---|---|
| term, field `name` | `PATCH /api/terms/{term_id}` (`server/terms/router.py:205`) | `{"name_certified": bool}` (`TermUpdate`, `:34`) |
| term, field `description` | same | `{"description_certified": bool}` |
| column_attribute | `PATCH /api/terms/{term_id}/column-attributes/{attr_id}` (`server/terms/router.py:116`) | `{"certified": bool}` (`ColumnAttributeUpdate`, `:42`) |
| sql_attribute | `PATCH /api/sql-attributes/{attr_id}` (`server/sql_attributes/router.py:193`) | `{"certified": bool}` (`SqlAttributeMetadataPatch`, `:52`) |

The same routes and bodies appear in `docs/openapi/auto-ontology-api.json` (paths at lines 6185, 7482, 7694; schemas at 13722, 8648, 11980). `true` is planned only for `certified` targets; `false` for `revoked`; `stale` and `failed` are listed under `withheld` unless `--unset-stale`. Default is a dry run. `--apply --base-url URL` sends ready requests with the token from `AUTO_ONTOLOGY_API_TOKEN` in the `x-api-key` header (their documented `ApiToken` scheme); the token is never printed, logged or returned. Tests check the planned paths and body fields against that OpenAPI file, and run the CLI with `--apply` against a local stub server to check that the token appears in neither stdout nor stderr.

**Limits**

- Path ids are live ids. Import stores the YAML id as `imported_id` and gives the row a server-generated UUID (`dal/schema.py:105-118`, `dal/model_interchange.py:776`), and no route returns `imported_id`. You supply `--id-map {imported_id: live_id}`; unmapped targets get a `{live_id_of:...}` placeholder and are never sent.
- The PATCH routes are not transactional across targets: an apply that fails half-way leaves half the flags set. Re-running `cert-status --apply` converges, because the plan is recomputed from the log.
- The log is a local file. It has no locking for concurrent writers and no signature; actor names are whatever `--actor` says.
- Auto Ontology does not read our log, so someone editing a flag in its UI is not recorded here. Re-applying the plan resets the flag to what the receipts support.

## 2. Evidence in answers

Theirs: `class DataAnswer(BaseModel):` (`mcp/auto_ontology_mcp/chat.py:46`), with fields `answer, sql, rows, row_count, truncated, reasoning`. Their skill says the graph paths it offers "are semantic relationship paths, not generation provenance" (`skills/nvidia-ontology-management/SKILL.md:111`).

**What ours does** (`evidence.py`). Given the `DataAnswer` (bare, or inside an MCP `structuredContent` / text-content wrapper), the model YAML and the certification log, it returns the original answer unchanged plus:

- `tables_used` and `columns_used`, from a stdlib tokenizer (comments, quoted strings and identifiers skipped) and heuristics: `FROM` lists, every `JOIN` form, `AS` and bare aliases, `WITH [RECURSIVE]` CTE names (not reported as tables), subqueries, `db.schema.table` names, `alias.column` references. Columns are kept only when the model YAML lists them on that table.
- `term_ids`: the YAML ids of terms that REPRESENT a used table or have a column attribute on a used column; `certification_state` gives each one's `name` and `description` state and each matched column attribute's state.
- `provenance_verdict`: `stale` if any matched unit is stale; else `grounded_in_certified` when every matched term description and column attribute is certified; `partially_certified` when some are; `uncertified` when none are or nothing matched.
- `snapshot` (from a snapshot JSON or the `code.snapshot` row in the DuckDB file), `model` (path and SHA-256), `generated_at`, and `sql_analysis` with what was not resolved.

**How it plugs in.** Run it on the result of their MCP `ask_question` tool. It makes no call to Auto Ontology.

**Limits.** These are candidate references inferred from returned SQL, not a trace of the definitions the agent retrieved or relied on. The verdict scores matched units only; unresolved dependencies can remain even when it says `grounded_in_certified`. Not a SQL parser. Unqualified columns are attributed only when the query has one table and no CTEs; otherwise they are listed as `unattributed_columns`. `SELECT *` is not expanded, table functions and `USING (col)` are not resolved, and alias scoping is flat (an alias reused for different tables in two subqueries resolves to the last). The certification state is from our log, not from Auto Ontology's flags. Term name certification is reported but not scored in the verdict.

## 3. Reconciliation

Theirs: `def upsert_table_term(` (`auto_ontology/dal/terms.py:417`). When another table owns a term name, it tries `name`, then `name (db.schema.table)`, then `name (table_id)` (`:462-466`), and inserts the first free one. The rule and its reason are documented in the function's docstring (`:423-428`): qualifying a colliding name keeps the global `(name, source)` constraint and name-based attribute lookups unambiguous. The table that is compiled first keeps the bare name; no per-term record of the rename is stored.

**What ours does** (`reconcile.py`). Each definition `{source, name, aliases, definition, canonical_id?}` is placed by the first step that applies, in a fixed order:

1. its `canonical_id`;
2. canonical name: its name equals the name of exactly one canonical term;
3. declared resolution: an entry keyed `source:name`, `name`, `source:alias` or `alias`, which must carry `resolved_to`, `reason` and `decided_by` (entries missing any are returned under `rejected_resolutions` and not used);
4. unique alias: its name or an alias matches the aliases of exactly one canonical term;
5. otherwise a lone definition becomes a `new_terms` proposal, and definitions sharing a name, or matching several canonical terms, are returned in `ambiguous` with every candidate.

A name changes only when a declared resolution supplies `name`, and the change is recorded under the term's `renames` with its reason and decider. Terms that still share a display name are listed in `name_collisions`, so you can settle names before Auto Ontology's `(name, source)` constraint does it for you. Assignment uses the stated precedence. When definitions share a canonical ID but have different display names, the first supplied name currently wins.

`governance/examples/worked_example.json` (regenerate with `python -m code_ontology_bridge.governance.examples.build_worked_example`) shows three runs next to their behaviour: two tables defining "revenue" differently, first ambiguous, then placed by declared resolutions; two modules both called `utils`, kept apart by their paths with a bare "utils" mention returned as ambiguous; and two real `service.py` modules from their repository with their real docstrings, flagged as a name collision.

**How it plugs in.** Run it on the definitions before building the model YAML; feed the resolved ids into `imported_id` and the resolved names into `term.name`, then import with `replace=false`.

**Limits.** Names are compared after lower-casing and treating `_`, `-` and spaces alike; there is no fuzzy matching. Definition text is never compared for meaning, only flagged when it differs (`definitions_differ`). It does not see terms already in Auto Ontology unless you include them as definitions.

## Design notes

- Receipts: a check passing, the event recorded in an append-only receipt log, and the flag set on Auto Ontology are kept as separate states, and the flag is planned only from the recorded event.
- Identity resolution follows a declared-resolution vocabulary: a fixed precedence order, with a collision returned as ambiguous rather than settled by renaming.
- Freshness is a content fingerprint over sorted relative paths and file hashes (absent files included), so it does not depend on modification times.

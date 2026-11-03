# Live run against Auto Ontology

NVIDIA Auto Ontology at commit `cdaf61e`, run natively on macOS (no Docker): their FastAPI backend, their ingestion service and their Alembic migrations, against a local PostgreSQL 17 with `pg_trgm` and pgvector. Our code ontology (`auto_ontology_code.model.yaml`, `auto_ontology_code.duckdb`) went in through their own routes. Every request and response is saved under `responses/`.

Steps 1 to 9 use no model key. Step 10 used Will's NVIDIA key by reference; see "With a model key".

## Reproduce

```sh
brew install postgresql@17 pgvector          # once; pgserver's PostgreSQL 16 has no pg_trgm (see Setup)
sh examples/auto-ontology/live/run_live.sh   # about one minute; stops every process it starts
```

`AUTO_ONTOLOGY_CLONE` points at their clone, `PG_BIN` at a PostgreSQL 17 bin directory, `PG_PORT` defaults to 54329. The script drops and recreates its databases on each run, so the ids in `responses/` change between runs.

Two Postgres databases in one local cluster (`.pgdata/`, gitignored):

- `auto_ontology`: empty store, then our model import (steps 1–3, 6, 7);
- `auto_ontology_g10`: DuckDB source connected and ingested first, then our model import (steps 4, 5, 8, 9).

## Setup findings

| What | Outcome | Evidence |
|---|---|---|
| `pgserver` (PostgreSQL 16.2) | Their first migration runs `CREATE EXTENSION pg_trgm`; pgserver ships only `plpgsql` and `vector`, so `alembic upgrade head` fails | `evidence/pgserver_pg16_lacks_pg_trgm.log` |
| Homebrew `postgresql@17` + `pgvector` 0.8.7 | Migrations run to `99d4d343dd0b`; matches their compose image (`pgvector/pgvector:pg17`) | `logs/alembic_*.log`, `responses/00_postgres_version.txt` |
| Our DuckDB file in their connector | **Refused.** Our export runs under duckdb 2.0.0 and their lockfile pins 1.5.5: "Trying to read a database file with version number 999, but we can only read versions between 64 and 68" | `evidence/duckdb_2.0_file_refused_by_their_duckdb_1.5.5.log` |
| Copy with `STORAGE_VERSION 'v1.5.0'` | Their duckdb 1.5.5 reads it: 8 tables, 2 views, 18 PK/FK constraints, the same as the source | `make_compat_duckdb.py`, `responses/05a_compat_duckdb_copy.json` |
| Feature flags | Read from the Prisma-owned `frontend.configurations`, which nothing creates without the Next.js frontend; every flag reads as off | `sql/frontend_configurations.sql` creates the table and turns semantic compilation on |

## Steps

| # | Command (all in `run_live.sh`) | Outcome | Evidence |
|---|---|---|---|
| 1 | `GET /api/health` on `uvicorn auto_ontology.server.__main__:create_app --factory --host 127.0.0.1 --port 3001` | 200; postgres ok; migrations ok at `99d4d343dd0b` | `responses/01_health.json` |
| 2 | `POST /api/model/import?replace=false&embed=false`, YAML as the raw body (`application/x-yaml`) | 200. Created 1 database, 1 schema, 10 tables, 67 columns, 8 terms, 43 column attributes, 10 semantic FKs, 7 custom analyses; nothing skipped; format `auto_ontology`. Every count equals the YAML | `responses/02_model_import.json` |
| 2 | `GET /api/terms`, `/api/terms/{id}`, `/api/terms/{id}/column-attributes`, `/api/exploration/semantic-graph`, `/api/exploration/graph`, `/api/exploration/edges`, `/api/datasources/dbs` | All 200. 8 terms; "Source file" has 9 column attributes and 4 related terms; semantic graph 8 nodes, 6 links (`SEMANTIC_FK`, `REPRESENTS`, `HAS_ATTRIBUTE`); exploration edges carry our 10 declared FKs and our custom-analysis SQL | `responses/02a`–`02g` |
| 2 | Postgres, `sql/store_counts.sql` and `sql/catalog_keys.sql` | Every catalog row, term, column attribute and custom analysis has its `cob:` id in `imported_id` (67/67 columns, 8/8 terms, 43/43 attributes, 7/7 analyses). 10 `column__foreign_key`, 10 `column__semantic_fk`, 43 `column__has_attribute`, 8 tables with a PK. All 8 terms have `source = 'semantic'` (G11) | `responses/02h`, `02i`, `02j` |
| 3 | G9: count `imported_id` in every step-1/2 response body | **0** in every response. It is stored (step 2) but not returned | `responses/03_g9_imported_id_in_responses.json` |
| 4 | G10, store `auto_ontology_g10`: connect the DuckDB source via `CONNECTION_STRINGS`, ingest, then the same import | **500 Internal Server Error** (not 422): `UniqueViolation ... "uq_catalog_database_name" Key (name)=(auto_ontology_code)`, raised at `dal/model_interchange.py:831` in `_resolve_entities_batch`. The transaction rolls back; the store is unchanged | `responses/04e`, `04f`, `04g` |
| 4 | Registering DuckDB through the UI route, `POST /api/connections/test` with `{"type":"duckdb",...}` | 422 "Unsupported connection type: 'duckdb'". DuckDB connects only through `CONNECTION_STRINGS` (`/api/connections/source` returns `true`) | `responses/04b`, `04c` |
| 4 | Workaround: replace the YAML's catalog ids with the live ids by name (`remap_catalog_ids.py`), import again | 200. Database, schema, 10 tables, 67 columns skipped as existing; 8 terms, 43 attributes, 10 semantic FKs, 7 analyses created; 10 declared FKs added. The importer stamped `imported_id` onto the existing catalog rows. Tables keep **no PK**: skipped tables are not updated | `responses/04h`, `04i`, `04j` |
| 5 | Ingestion service (`python -m auto_ontology.ingestion_service`, `CONNECTION_STRINGS=duckdb:///…/.work/auto_ontology_code.duckdb`), startup pass | Catalog written: 10 tables (8 tables + 2 views), 67 columns. **0 primary keys, 0 foreign keys** (their DuckDB connector reports none). Embedding then fails with 401 (no key) and is logged; the catalog stays | `responses/05b`, `05c`, `05d`, `logs/ingestion_db2.log` |
| 6 | Routes in their MCP allow-list (`mcp/auto_ontology_mcp/tools.py:59`) on the imported model | Work with no key: `search_terms` (`GET /api/terms?query=symbol` → "Code symbol"), `get_term`, `get_term_columns`, `get_term_sql_attributes` (0: the model has none), `get_sql_attribute` (404 for an unknown id), `describe_table` (6 queries, 1 term), plus the readiness probes and global search. Needs a key: `check_answerable` (`POST /api/question-entity-coverage`) → 422 "LLM client is not configured." | `responses/06a`–`06j` |
| 7 | `cob certify` (4 targets, `cert_targets.json`) → id map from Postgres → `cob cert-status --plan-patches --id-map` | 3 certified (gold SQL reproduces 22/22 and 3/3), 1 failed by design and withheld. 3 PATCH requests planned, all ready | `cert/events.jsonl`, `cert/id_map.json`, `cert/plan.json` |
| 7 | `cob cert-status ... --apply --base-url http://127.0.0.1:3001` with no token | Exit 2, "set AUTO_ONTOLOGY_API_TOKEN to apply; nothing was sent". Our CLI requires a token even though the internal service does not check one | `cert/apply_attempt.stdout` |
| 7 | Same 3 PATCH bodies sent to FastAPI with no token and no user header (`apply_plan_no_token.py`) | All 200. Postgres: `files.package.certified` false→true, `calls.name_certified` false→true, `symbols.description_certified` false→true; the withheld target stays false. `GET /api/terms/{id}` then shows `certification: "partial"`. `modified_by` stays null | `responses/07a`, `07b`, `07c_patch_no_header/`, `07e` |
| 7 | Same PATCHes with `x-auto-ontology-user-id: live-run:code-ontology-bridge` | All **403** "You do not have permission to edit this". With the header, `enforce_edit` (`server/owners.py:95`) checks the user's role, and an id unknown to their user tables has none. Without the header there is no check at all | `responses/07d_patch_with_user_header/` |
| 8 | `POST /api/chat/completions` (the route behind MCP `ask_question`) for Q1, no key | Stream completes with HTTP 200; the graph reaches `unconstructable_sql_response` twice; result "LLM failed to produce a response." | `responses/08_ask_no_key/ask_q1.json` |
| 9 | `POST /api/semantic-compilation/trigger`, flag off, then on | Off: skipped ("compilation disabled in settings"). On, no key: the two views without terms fail with `REASONING_API_KEY is not set`; semantic FK inference is skipped (`EMBED_API_KEY not set`); the compiler **removed our imported semantic FK `headings.file_id → files.file_id`** because the column has no values (the `headings` table is empty in this example). Semantic FKs 10 → 9 | `responses/09a`, `09c`, `09d`, `09e` |
| — | Secret scan (`grep -c nvapi-`) over `responses/`, `logs/`, `cert/` | none | `responses/99_secret_scan.txt` |

## With a model key (3 Nov)

Will's NVIDIA key was passed by reference with `--with-key <env file>`: it was read inside the subshell that starts each of their processes and never printed or written. After the run, no file here contains a string of the form `nvapi-` followed by key characters.

| What | Outcome | Evidence |
|---|---|---|
| Their documented default chat model, `nvidia/nemotron-3-nano-30b-a3b` (`.env.example`) | Every chat call returned **`410 Gone`**: the model is no longer served on `integrate.api.nvidia.com` and is absent from `GET /v1/models`. All five questions ended "LLM failed to produce a response." Observed on the first keyed run; its logs were overwritten by the rerun below | session record |
| Probe of current models (one 5-token call each) | `nvidia/nemotron-3.5-lightning-30b-a3b` 200; `nvidia/nemotron-3-super-120b-a12b` 404; `nvidia/nemotron-nano-3-30b-a3b` 404; `openai/gpt-oss-20b` 504 | session record |
| Rerun with `AO_CHAT_MODEL=nvidia/nemotron-3.5-lightning-30b-a3b`: ingestion with embeddings, import with `embed=true` | Embeddings and import work (200) | `responses/10a`, `10c` |
| Semantic compilation | Reports "10 table(s) compiled … finished successfully" while the same log holds 24 structured-output errors. The compiler again removed the imported semantic FK on the empty `headings.file_id`. Terms 8 → 18 (10 generated), column attributes 43 → 100 | `logs/ingestion_keyed.log`, `responses/10g` |
| Structured output | The hosted model rejects their default structured-output request: `[400] unknown field guided_json` (113 times in the backend log). `_structured_output_kwargs` in `auto_ontology/utils/llm_invoke.py` chooses `function_calling` only for Claude models; every other model gets LangChain's default, which for `ChatNVIDIA` sends `guided_json`. Each failure costs about two minutes of retries before a fallback | `logs/backend_keyed.log` |
| `check_answerable` for "Which functions call upsert_table_term?" | Coverage 1.0, but the candidates are two attributes of the term "Import statement" (`is internal`, `module name`), not of the call table | `responses/10h` |
| `ask_question`, Q1 | After about 45 minutes Q1 was still in SQL repair, and the run was stopped. At that rate the five questions would take about four hours | `logs/backend_keyed.log` |

Through NVIDIA's public API, with a model that is currently served, their pipeline ingests, embeds, imports and compiles our code ontology, but the text-to-SQL agent cannot use structured output and does not finish in practical time. Their README's tested configuration is a different route: an `sk-` key on `inference-api.nvidia.com` with Claude models, for which `function_calling` is selected.

A possible fix on their side, untested here: select `method="json_mode"` or `"function_calling"` in `_structured_output_kwargs` for `ChatNVIDIA` models that reject `guided_json`, and update the default chat model in `.env.example`.

Not run: their benchmark (`NVIDIA/auto-ontology-eval`).

## What this changes in GAPS.md

- Header line "No row has been run against a live Auto Ontology server": G1, G2, G9, G10 and G11 have now been run, and G3, G4 in part. The run needed no Docker; it used Homebrew PostgreSQL 17.
- **G1**: run live, with a new gap. Their connector refuses our file as written, because duckdb 2.0.0 writes a storage version 1.5.5 cannot read. The existing test passes because it loads their connector under our duckdb. Fix in our exporter: write with `ATTACH ... (STORAGE_VERSION 'v1.5.0')`, or pin `duckdb<2` for the export, and run the test under their lockfile's duckdb. After that, ingestion catalogues 10 tables and 67 columns with 0 keys.
- **G2**: run live. Ingestion gives 0 PKs and 0 FKs. Model import onto an empty store gives 10 FKs and 8 PKs. Import onto an ingested catalog (with remapped ids) adds the 10 FKs, but PKs stay empty. Compilation without a key removed one imported semantic FK (`headings.file_id`) because its column is empty. Imported semantic FKs are therefore not durable when a column has no data.
- **G3/G4**: the PATCH routes on the internal service accept our planned requests with no token, and the flags change in Postgres. `modified_by` is set only from `x-auto-ontology-user-id`, and an unknown user id gets 403. Recording our actor in their row therefore needs a real user in their user tables.
- **G9**: run live. `imported_id` is stored on every imported row and appears in 0 response bodies.
- **G10**: run live and confirmed, as a 500 rather than a 422, at `dal/model_interchange.py:831`. A tested workaround exists: give the YAML the live catalog ids (`remap_catalog_ids.py`). G10 also does not cover a second gap: DuckDB cannot be registered through `/api/connections` ("Unsupported connection type"), only through `CONNECTION_STRINGS`.
- **G11**: run live. All 8 imported terms have `source = 'semantic'` in Postgres.

## Follow-up changes outside this folder

- Done: the DuckDB exporter writes storage version v1.5.0, which their pinned duckdb 1.5.5 reads; `tests/export/test_duckdb.py` opens the export with duckdb 1.5.5. `make_compat_duckdb.py` is no longer needed for new exports.
- Done: `cob cert-status --apply --internal [--user-id ID]` sends to the internal FastAPI service without a token, so `apply_plan_no_token.py` is no longer needed.
- Open: `cob export-model` could take a live-id map for catalog rows, the role `remap_catalog_ids.py` plays here, so a model can be imported onto an already connected source.

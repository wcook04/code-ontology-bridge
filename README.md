# code-ontology-bridge

An ontology of a codebase for [NVIDIA Auto Ontology](https://github.com/NVIDIA/auto-ontology), delivered through the entry points Auto Ontology already has. The worked example is Auto Ontology's own repository, mapped into tables that Auto Ontology can connect to, import and benchmark on.

> What would be affected if `resolve_semantic_fks` changed?
> `_run_semantic_compilation` calls it (depth 1); `run_semantic_compilation` calls that (depth 2); `main` calls that, and `SemanticScheduler._run_once` hands it to `asyncio.to_thread` (depth 3).

Auto Ontology's own agent gave that answer, writing a recursive SQL query over the code map in this repository, and it matches the source. Asked 22 such questions about its own code, it gave the right content for 21 ([results](examples/auto-ontology/live/RESULTS.md)).

## What it adds

Auto Ontology builds a context layer for agents over relational databases: terms, attributes, metrics and joins, served through MCP. This repository brings two things to it.

**A code map as data.** For each Python file: its description, taken word for word from the module docstring; its functions, methods and classes, with their base classes; the calls between them, including functions handed on as callbacks; imports; and which tests cover which files. A snapshot row records the repository, the commit and a fingerprint of the source. The map is eight tables with declared primary and foreign keys.

**A record behind each certification.** Auto Ontology stores whether a term, column attribute or SQL attribute is certified, and who last edited it. The governance layer adds:

- a certification history: which check passed, who or what ran it, and the source fingerprint and commit it was checked against. A certification goes stale when the file changes, and a revoke records what it rolls back to;
- answers that carry their evidence: the tables, columns and terms an answer used, whether each is certified, and the snapshot it came from;
- reconciliation of competing definitions in a fixed order, where each resolution states its reason and an unresolved clash is reported as ambiguous.

[`GAPS.md`](GAPS.md) lists each capability with what Auto Ontology's code does today (file and line at commit `cdaf61e`), what this repository adds, and how each claim was checked.

## How it plugs in

No change to Auto Ontology is needed for any of these.

| Entry point in Auto Ontology | Output | How |
|---|---|---|
| DuckDB connector, their reference `SQLDatabase` | `auto_ontology_code.duckdb`, schema `code` | `CONNECTION_STRINGS=duckdb:///abs/path/auto_ontology_code.duckdb` |
| Benchmark datasets in [`NVIDIA/auto-ontology-eval`](https://github.com/NVIDIA/auto-ontology-eval) | `auto_ontology_code/` with `ddl/`, `data/`, `evaluation.json`, `custom_analyses.json` | copy into `datasets/`, then their seed script with `--database-name auto_ontology_code` and their benchmark |
| Model import, `POST /api/model/import` | `auto_ontology_code.model.yaml` | import with `replace=false` on a store where this database is not already connected |
| Certification routes (`PATCH /api/terms/{id}`, `/api/terms/{id}/column-attributes/{attr_id}`, `/api/sql-attributes/{id}`) | requests planned from passing checks | `cob cert-status --plan-patches`; `--apply` sends through the gateway with a token, or with `--internal` to the FastAPI service |
| MCP `ask_question` result | evidence-carrying answer | `cob enrich-answer` |

## The worked example

`examples/auto-ontology/` holds the code map of [NVIDIA/auto-ontology](https://github.com/NVIDIA/auto-ontology) at commit `cdaf61e`:

| | |
|---|---|
| Python files | 473, of which 168 are tests; none omitted |
| Functions, methods and classes | 5,319 |
| Base-class links | 306, of which 146 point to a class in the repository |
| Direct call sites inside functions and classes | 31,178 |
| Functions passed on as callbacks | 57 |
| Imports | 4,762 |
| Test links | 483 |
| Files with a description from their docstring | 399 (84.4%); the other 74 are left empty |

Each direct call site inside a function or class is kept and classified. A call gets a target only when this analysis finds the target in the repository:

| How the call was resolved | Share |
|---|---|
| Method on an object whose type this analysis does not infer | 37.8% |
| Into an outside library (`pandas`, `sqlalchemy`, `logging`, …) | 17.4% |
| Into another file of the repository, through an import | 15.5% |
| Within the same file | 14.0% |
| Python built-in (`len`, `str`, …) | 13.4% |
| Left unresolved | 1.1% |
| Method on `self` | 0.8% |

The benchmark set has 22 questions with reference SQL (11 simple, 6 moderate, 5 challenging), for example the blast radius of a function, public functions with no linked test, and packages that call into each other in both directions. There are 7 named analyses, including blast radius, untested public API, most-called functions and undocumented modules. The recorded answers come from the reference SQL.

## Run it

Requires Python 3.12, [uv](https://docs.astral.sh/uv/) and a checkout of Auto Ontology.

```bash
uv sync
export AUTO_ONTOLOGY_CLONE=/path/to/auto-ontology
sh examples/auto-ontology/reproduce.sh "$AUTO_ONTOLOGY_CLONE"   # build and all three exports
uv run pytest -q
```

With `AUTO_ONTOLOGY_CLONE` set, all 62 tests run. Without it, the tests that load Auto Ontology's code are skipped.

Rebuilding the same commit gives the same rows. The JSON, CSV, SQL and YAML outputs are byte-identical; the DuckDB file holds identical rows.

`cob --help` lists the commands: `build`, `export-duckdb`, `export-dataset`, `export-model`, `certify`, `cert-status`, `enrich-answer` and `reconcile`. To map another repository, run `cob build <checkout> --out codemap.json` and then the exports.

## What the tests check against Auto Ontology's code

- Their `DuckDBDatabase` class, loaded from their source, reads our file with `get_tables`, `get_columns`, `get_views` and `execute`.
- The model YAML validates against their `AutoOntologyModelDocument` and dumps back unchanged.
- The dataset folder loads into PostgreSQL 16 in the same order as their seed script, and every reference query returns the same rows there as in DuckDB.
- The planned certification requests use paths, body fields and the `x-api-key` scheme that appear in their OpenAPI file.

The tests also check that every reference query reproduces its recorded answer, and that `--apply` never writes the API token to its output.

## Run against a live Auto Ontology

[`examples/auto-ontology/live/`](examples/auto-ontology/live/RESULTS.md) runs Auto Ontology's FastAPI backend and ingestion service natively (no Docker) on PostgreSQL 17 with pgvector, and loads this repository's outputs through their routes. `run_live.sh` reproduces every step; the evidence (requests, responses, logs) is committed.

What ran:

- The model import creates every table, column, key, term, attribute and analysis from the YAML. Their term, attribute, graph and table routes return them, and so do the read-only routes behind their MCP tools.
- Ingestion of the DuckDB file through their connector catalogues all 10 tables and views.
- Certification requests set Auto Ontology's flags through its own PATCH routes, and a failed check is withheld.
- With an NVIDIA API key, embeddings, import with embeddings and semantic compilation complete on the code ontology.

Getting their question-answering agent to work through public model APIs surfaced four issues on Auto Ontology's side, recorded as G12 to G15 in [`GAPS.md`](GAPS.md): the default chat model in `.env.example` is no longer served, the current Nemotron model's reasoning outlasts the structured-output timeout, compilation reports success when its model calls fail, and questions about code are routed to the metadata agent. [`upstream-fix/`](examples/auto-ontology/live/upstream-fix/README.md) is a 9-file patch for the first, second and fourth, with tests, that passes their lint, format and test checks.

With that patch and DeepSeek V4.1 Flash through OpenRouter, their agent answered all 22 benchmark questions about its own source: 13 fully right, 8 with the right items but a count column left out, and 1 wrong. The questions, its SQL, its answers and three-way scores are in [`RESULTS.md`](examples/auto-ontology/live/RESULTS.md). The whole run cost $0.54.

Not yet run: their benchmark harness (`NVIDIA/auto-ontology-eval`) end to end, and their tested configuration (Claude models on NVIDIA's inference gateway), which needs NVIDIA access.

## Limits

- Python only, and static analysis only. Functions passed directly as call arguments are followed at low confidence; calls through overridden methods, references stored in lists, dicts or variables, and calls made through strings are not.
- Calls at module level, outside any function or class, are counted in the snapshot's known limits and left out of the call table.
- Descriptions are docstring text as written. Nothing is generated.
- The governance layer parses SQL with a small heuristic parser; [`docs/governance.md`](docs/governance.md) lists what it does not handle.
- `imported_id` is not returned by Auto Ontology's API, so certification requests take a map from imported ids to live ids.

## Background

The code map follows the Code Map in Will Cook's own development system, where files carry fixed description headings and agents and people read the same saved descriptions. A walkthrough is on YouTube: [CodeMap: finding my way through code written with AI](https://www.youtube.com/watch?v=OnBO9U9T2IQ). Files that use those headings (`[PURPOSE]`, `[INTERFACE]`, `Teleology:` and others) have them stored in `code.headings`. Auto Ontology's repository uses plain docstrings, so that table is empty in the worked example.

## Licence

Apache License 2.0, the same licence as Auto Ontology.

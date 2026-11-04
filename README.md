# code-ontology-bridge

**An independent Python-source adapter for NVIDIA Auto Ontology.**

This project makes Python source queryable through [Auto Ontology](https://github.com/NVIDIA/auto-ontology)'s existing database and semantic-model interfaces. The bridge extracts files, functions, classes, calls, imports and docstrings, then exports a DuckDB database and model YAML describing its tables and joins. NVIDIA supplies semantic retrieval, SQL generation and query execution.

**A working example:** we mapped Auto Ontology's own repository, containing 473 Python files and 5,319 symbols. Given explicit reverse-traversal and callback guidance, its agent generated recursive SQL that returned four callers of `resolve_semantic_fks`, including a callback reference recorded from `asyncio.to_thread`.

[Inspect the exact request, SQL and rows](examples/auto-ontology/live/current/responses/10i_ask_with_key/ask_q11.json) · [Read the paper](docs/case-study.md) · [Download the PDF](docs/case-study.pdf) · [Build the exports locally](#build-the-exports-locally)

Extraction and export run without model credentials or changes to NVIDIA's code. The recorded live agent run required a separate compatibility patch against a pinned revision. The evaluation uses development questions, not an independent accuracy benchmark.

## What each part contributes

| Component | Responsibility |
| --- | --- |
| **NVIDIA Auto Ontology** | Retrieves semantic context, generates SQL and executes it through its database connectors. |
| **This bridge** | Extracts Python source facts and exports the rows, table descriptions and relationships that make them queryable. |
| **Compatibility patch** | Configures public model clients and forwards the existing SQL-only route through the chat API for the recorded run. |

## One question, all the way through

Start with this operation in the pinned scheduler, at line 203:

```python
tables_processed = await asyncio.to_thread(
    run_semantic_compilation, database_name
)
```

The extractor records it in `code.calls` with `call_kind: callback`,
`resolution: imported`, and `confidence: low`. The caller is
`SemanticScheduler._run_once`; the callee is `run_semantic_compilation`.
The row records a function passed as an argument, not an observed execution.

The following is a short paraphrase, not the complete submitted request:

> Which callers reach `resolve_semantic_fks`, directly or indirectly, outside tests, and at what shortest depth?

The submitted request specified exact output fields and explicitly instructed the agent to follow resolved calls backwards, recursively, including callback references. With that guidance, Auto Ontology generated recursive SQL and returned four callers. The diagram uses short role names: arrows point toward the foreign-key resolver, and the query follows them in reverse. The dashed edge is a callback reference; solid edges are direct calls.

![The scheduler and main are three edges from resolve_semantic_fks; run_semantic_compilation is two edges away and _run_semantic_compilation is one. The scheduler edge is a callback reference; the other edges are direct calls.](docs/figures/caller-chain.png)

[Open the diagram at full size](docs/figures/caller-chain.png).

| Caller role | Depth |
| --- | ---: |
| Compiler | 1 |
| Wrapper | 2 |
| Scheduler | 3 |
| CLI entry | 3 |

<details>
<summary>Exact source symbols</summary>

| Diagram label | Source symbol |
| --- | --- |
| Scheduler | `SemanticScheduler._run_once` |
| CLI entry | `main` |
| Wrapper | `run_semantic_compilation` |
| Compiler | `_run_semantic_compilation` |
| FK resolver | `resolve_semantic_fks` |

The resolver is the query's starting point, not a returned caller.

</details>

The scheduler passes the wrapper to `asyncio.to_thread`. Recording that callback reference lets the query reach the scheduler as well as ordinary callers. The [saved response](examples/auto-ontology/live/current/responses/10i_ask_with_key/ask_q11.json) contains the question, generated SQL, complete symbol IDs and returned depths.

This demonstrates querying recorded relationships, not independently discovering the traversal strategy. These are relationships in a static source map; the diagram does not show observed execution or establish complete runtime impact analysis.

## How the exports connect

![The bridge exports DuckDB rows and model YAML separately. Auto Ontology imports the model for semantic context and queries the rows through its existing DuckDB connector.](docs/figures/architecture.png)

[Open the architecture diagram at full size](docs/figures/architecture.png).

The two exports have different jobs: **DuckDB supplies data; model YAML explains it**. Importing YAML alone does not connect a database. A third export supplies DDL, CSV data and reference questions in NVIDIA's evaluation format; the full upstream benchmark harness has not been run.

**A function is a row; Code symbol is a semantic term.** The frozen native model
maps `cob:auto_ontology_code:term:symbols` to
`cob:auto_ontology_code:table:code.symbols`. Call site maps to `code.calls`;
semantic foreign keys connect its caller and callee columns to the symbol-ID
attribute. The model has eight entity terms, not one term per function.
A function's docstring is a data value in `summary`; the authored description of
that column explains what the value means.

[Inspect the frozen model YAML](examples/auto-ontology/live/current/inputs/model.yaml)
or use the [model and Q11 inspection resources](docs/inspection-api.md).
The exported YAML, remapped import payload and compiled catalog are separate
stages; the inspector marks uncaptured stages explicitly.

The source-map approach comes from **CodeMap**, Will Cook's earlier source-navigation tool. This package adapts it into a standalone extractor. It reads existing docstrings, preserves missing descriptions as empty values and requires no private CodeMap service.

Separate [governance commands](docs/governance.md) record checks and annotate SQL; they do not enforce certified-only querying.

## What the experiment established

The complete run on 4 November 2026 used DeepSeek v4.1 Flash through OpenRouter, NVIDIA embeddings and reranking, and SQL routing for all 22 questions. Every request specified required output fields; 18 included hints. Reference SQL and answer values were kept out of requests, and no saved example analyses were imported.

| Result | Count |
| --- | ---: |
| Completed requests | 22/22 |
| Matching result tables | 21/22 |
| Matching tables with substantive explanations | 20/22 |

Q2 selected an extra package. Q14 returned the correct rows but only “thought” as its prose. Both remain in the [detailed results](examples/auto-ontology/live/RESULTS.md), alongside every other answer. There is no held-out set or schema-only control. The next test should compare schema-only and semantic-layer context on independent questions.

<a id="serve-data-for-a-website"></a>

## Inspect the saved evidence

The backend exposes file and symbol search, package counts, call neighborhoods, source links and the retained evaluation. Build the NVIDIA example directly from the committed exports; this needs no model credentials:

```sh
uv run cob inspect-export \
  --dataset examples/auto-ontology/auto_ontology_code \
  --evidence examples/auto-ontology/live/current \
  --case examples/auto-ontology/live/caller-chain-case.json \
  --out build/inspection/bundle.json
uv run cob inspect-publish --bundle build/inspection/bundle.json --out build/publication
uv run cob inspect-serve --bundle build/inspection/bundle.json
```

Open `http://127.0.0.1:8767/api/v1` for the JSON route index. The new `build/publication/` directory contains a small manifest, a Q11 reading path, separate model/source resources and all 22 recorded answers. The complete bundle remains available. Use a new output directory for each publication build. The service reads saved data; it does not ask a model new questions. See the [backend contract and frontend handoff](docs/inspection-api.md) for endpoints, graph limits and deployment options.

<a id="try-it-locally"></a>

## Build the exports locally

Extraction and export need no model API. Install [uv](https://docs.astral.sh/uv/) and use Python 3.12:

```sh
git clone https://github.com/wcook04/code-ontology-bridge.git
cd code-ontology-bridge
uv sync --locked
mkdir -p build
uv run cob build code_ontology_bridge --out build/codemap.json --summary build/summary.json
uv run cob export-duckdb --codemap build/codemap.json --out build/repository.duckdb
uv run cob export-model --codemap build/codemap.json --out build/repository.model.yaml --database repository
```

This maps the bridge's own package and produces a summary, a queryable DuckDB file and model YAML. Replace `code_ontology_bridge` with another Python source directory to change the input. Follow the [reproduction guide](docs/reproduction.md) to rebuild the pinned NVIDIA example. [Running the live NVIDIA integration](docs/reproduction.md#run-a-fresh-22-question-evaluation) is a separate procedure requiring credentials and the compatibility patch.

The extractor is a static-analysis prototype. Dynamic calls can be missed, callback references may never execute, and test links are associations rather than coverage. Repeated qualified definitions receive line-qualified IDs; ambiguous targets remain unresolved. See [source-analysis limits](GAPS.md#source-analysis-limits).

## Integration compatibility

| Activity | Requirements and evidence |
| --- | --- |
| Extract source and export DuckDB/model YAML | This package alone; no model credentials or NVIDIA modifications. |
| Reproduce the recorded live integration | Patched Auto Ontology at [`cdaf61e`](https://github.com/NVIDIA/auto-ontology/tree/cdaf61e1bd0cf3820d11d72b43bb460816aebbd3), PostgreSQL and model credentials. The patch configures public model clients and forwards SQL routing through the chat API. |
| Use a later upstream revision | Not validated by this recorded run. Check the patch and interfaces against that revision before treating it as compatible. |

[Reproduce the live NVIDIA integration](docs/reproduction.md#run-a-fresh-22-question-evaluation) · [Review the twelve-file patch and scoped tests](examples/auto-ontology/live/upstream-fix/README.md)

## Find your way around

| Location | What belongs there |
| --- | --- |
| [code_ontology_bridge/](code_ontology_bridge/) | Installable extractor, exporters, read-only inspection API, static publication builder and governance commands. |
| [docs/](docs/README.md) | Paper, PDF, explanatory figures and task-specific guides. |
| [eval/](eval/) | Authored questions, reference SQL, output contracts and optional example analyses. |
| [examples/auto-ontology/](examples/auto-ontology/) | Generated dataset and replay tools; [live/current/](examples/auto-ontology/live/current/) retains the complete run; the [Q11 descriptor](examples/auto-ontology/live/caller-chain-case.json) supplies the reading path. |
| [tests/](tests/) | Local behavior and optional upstream compatibility checks. |
| [tools/](tools/) | Repository checks and the paper builder. |
| [SPEC.md](SPEC.md) / [GAPS.md](GAPS.md) | Interface contract / capability status and remaining limits. |

Run `uv run pytest -q -ra` and `uv run python tools/check_repository.py` to check the checkout. See [contributing](CONTRIBUTING.md) for optional integration tests, figure maintenance and evidence-preservation rules.

## Licence

[Apache License 2.0](LICENSE). This is an independent integration with NVIDIA's open-source project.

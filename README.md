# code-ontology-bridge

**Let NVIDIA Auto Ontology query a Python codebase.** This bridge turns source files, symbols, calls and existing docstrings into a DuckDB database and a semantic model that [Auto Ontology](https://github.com/NVIDIA/auto-ontology) can use through its existing interfaces.

The worked example is Auto Ontology's own source: **473 files and 5,319 symbols**. Its agent traced a caller chain through an asynchronous callback and answered questions about imports, inheritance and test associations. One complete development run produced **21/22 matching result tables**, with substantive explanations for **20/22**. The questions informed development; this is an integration demonstration, not a held-out accuracy benchmark.

[Read the paper](docs/case-study.md) · [Download the PDF](docs/case-study.pdf) · [Inspect all 22 answers](examples/auto-ontology/live/RESULTS.md) · [Try it locally](#try-it-locally)

## One question, all the way through

> Which callers reach `resolve_semantic_fks`, directly or indirectly, outside tests, and at what shortest depth?

Auto Ontology generated recursive SQL and returned four callers. The diagram uses short role names: arrows point toward the foreign-key resolver, and the query follows them in reverse. The dashed edge is a callback reference; solid edges are direct calls.

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

The request included a hint about reverse traversal and callbacks. These are relationships in a static source map; the diagram does not show observed execution or establish complete runtime impact analysis.

## What each part contributes

| Component | Responsibility |
| --- | --- |
| **NVIDIA Auto Ontology** | Retrieves semantic context, generates SQL and executes it through its database connectors. |
| **This bridge** | Extracts Python source facts and exports the rows, table descriptions and relationships that make them queryable. |
| **Compatibility patch** | Configures public model clients and forwards the existing SQL-only route through the chat API for the recorded run. |

The source-map approach comes from **CodeMap**, Will Cook's earlier source-navigation tool. This package adapts it into a standalone extractor. It reads existing docstrings, preserves missing descriptions as empty values and requires no private CodeMap service.

![The bridge exports DuckDB rows and model YAML separately. Auto Ontology imports the model for semantic context and queries the rows through its existing DuckDB connector.](docs/figures/architecture.png)

[Open the architecture diagram at full size](docs/figures/architecture.png).

The two exports have different jobs: **DuckDB supplies data; model YAML explains it**. Importing YAML alone does not connect a database. A third export supplies DDL, CSV data and reference questions in NVIDIA's evaluation format; the full upstream benchmark harness has not been run.

For a maintainer reviewing the integration, start with the [exporters](code_ontology_bridge/export/), the [interface specification](SPEC.md) and the [twelve-file patch with scoped validation](examples/auto-ontology/live/upstream-fix/README.md). The patch adds no code-specific connector or query planner. Separate [governance commands](docs/governance.md) record checks and annotate SQL; they do not enforce certified-only querying.

## What the experiment established

The complete run on 4 November 2026 used DeepSeek v4.1 Flash through OpenRouter, NVIDIA embeddings and reranking, and SQL routing for all 22 questions. Every request specified required output fields; 18 included hints. Reference SQL and answer values were kept out of requests, and no saved example analyses were imported.

| Result | Count |
| --- | ---: |
| Completed requests | 22/22 |
| Matching result tables | 21/22 |
| Matching tables with substantive explanations | 20/22 |

Q2 selected an extra package. Q14 returned the correct rows but only “thought” as its prose. Both remain in the [detailed results](examples/auto-ontology/live/RESULTS.md), alongside every other answer. There is no held-out set or schema-only control. The next test should compare schema-only and semantic-layer context on independent questions.

## Try it locally

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

This maps the bridge's own package and produces a summary, a queryable DuckDB file and model YAML. Replace `code_ontology_bridge` with another Python source directory to change the input. Follow the [reproduction guide](docs/reproduction.md) to rebuild the pinned NVIDIA example or run the live service.

The extractor is a static-analysis prototype. Dynamic calls can be missed, callback references may never execute, and test links are associations rather than coverage. Repeated qualified definitions receive line-qualified IDs; ambiguous targets remain unresolved. See [source-analysis limits](GAPS.md#source-analysis-limits).

## Find your way around

| Location | What belongs there |
| --- | --- |
| [code_ontology_bridge/](code_ontology_bridge/) | Installable extractor, exporters and governance commands. |
| [docs/](docs/README.md) | Paper, PDF, explanatory figures and task-specific guides. |
| [eval/](eval/) | Authored questions, reference SQL, output contracts and optional example analyses. |
| [examples/auto-ontology/](examples/auto-ontology/) | Generated dataset and replay tools; [live/current/](examples/auto-ontology/live/current/) retains the complete run. |
| [tests/](tests/) | Local behavior and optional upstream compatibility checks. |
| [tools/](tools/) | Repository checks and the paper builder. |
| [SPEC.md](SPEC.md) / [GAPS.md](GAPS.md) | Interface contract / capability status and remaining limits. |

Run `uv run pytest -q -ra` and `uv run python tools/check_repository.py` to check the checkout. See [contributing](CONTRIBUTING.md) for optional integration tests, figure maintenance and evidence-preservation rules.

## Licence

[Apache License 2.0](LICENSE). This is an independent integration with NVIDIA's open-source project.

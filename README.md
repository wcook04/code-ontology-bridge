# code-ontology-bridge

Turn a Python repository into a database that [NVIDIA Auto Ontology](https://github.com/NVIDIA/auto-ontology) can query. The bridge extracts files, functions, calls and docstrings, then exports the data and its semantic model through Auto Ontology's existing interfaces.

The worked example is Auto Ontology's own source. Its question-answering agent used the resulting database to find callers of a function, trace package dependencies and inspect class inheritance.

[Read the case study](docs/case-study.md) · [Inspect the results](examples/auto-ontology/live/RESULTS.md) · [Try it locally](#try-it-locally) · [Reproduce the experiment](docs/reproduction.md)

## One question, all the way through

> Which functions call `resolve_semantic_fks`, directly or indirectly, outside tests, and at what shortest depth?

Auto Ontology's agent generated recursive SQL over the extracted call relationships and returned:

| Caller | Depth |
| --- | ---: |
| `_run_semantic_compilation` | 1 |
| `run_semantic_compilation` | 2 |
| `SemanticScheduler._run_once` | 3 |
| `main` | 3 |

The scheduler passes `run_semantic_compilation` to `asyncio.to_thread`. Recording that callback reference lets the SQL traversal reach the scheduler as well as ordinary callers. You can inspect the [question, generated SQL and returned rows](examples/auto-ontology/live/evidence/deepseek_22q_default_routing/10i_ask_with_key/ask_q11.json).

This answer came from the patched Auto Ontology agent using DeepSeek through OpenRouter, with NVIDIA embeddings and reranking. The request included a hint about reverse traversal and callbacks. These are callers in the recorded static map; the example does not establish a complete runtime impact analysis.

## What each part contributes

**NVIDIA Auto Ontology** helps agents answer questions about relational databases. It associates tables and columns with named concepts, descriptions, calculations and joins. Its agent retrieves that context, writes SQL and executes it against the connected data. Here, the data happens to describe software.

**CodeMap** is Will Cook's earlier source-navigation tool. It makes saved descriptions and static code connections available to people and coding agents. The bridge adapts that approach into a standalone Python extractor. It reads existing docstrings; it does not generate descriptions or require CodeMap's private interface.

**This bridge** supplies eight tables: files, docstring headings, symbols, class bases, calls, imports, test links and a source snapshot. A function is a row in the symbols table; a call connects two symbol rows. The semantic model describes those tables and their relationships so Auto Ontology can query them.

The exports have complementary jobs:

| Export | What it supplies |
| --- | --- |
| DuckDB database | The source-code rows and views, through Auto Ontology's existing connector. |
| Model YAML | Table descriptions, terms, attributes, joins and example analyses, through model import. |
| Evaluation dataset | DDL, CSV data and reference questions in NVIDIA's evaluation format. The full upstream benchmark harness has not been run. |

The data and model interfaces already existed upstream. The successful public-model question run also used a [compatibility patch](examples/auto-ontology/live/upstream-fix/README.md) for model configuration and routing. Importing the YAML alone does not connect a queryable database.

Separate [governance commands](docs/governance.md) record certification checks, annotate returned SQL and reconcile competing definitions. They are local additions; they do not make Auto Ontology enforce certified-only querying.

## What the experiment established

The recorded map covers 473 Python files and 5,319 symbols at a pinned Auto Ontology revision. The author supplied 22 questions and reference queries; 18 questions included hints.

| Stage | Complete normalized matches | Missing reference fields | Unmatched |
| --- | ---: | ---: | ---: |
| Initial 22-question run | 10 | 7 | 5 |
| After replacing five answers with SQL-route reruns | 11 | 8 | 3 |
| After two documented identity checks | 13 | 8 | 1 |

The identity checks reconcile module names with file paths and function names with full symbol identifiers. The eight partial results omit counts or other reference fields. The remaining failure queries an empty headings table instead of the function-summary column.

These numbers describe agreement between returned rows and reference rows on this snapshot. They are not a 95% exact-accuracy result or a single fresh run under one routing policy. There is no held-out question set or schema-only comparison. The useful result is that the existing database agent can answer structural code questions through this adapter. [The full results](examples/auto-ontology/live/RESULTS.md) explain the scoring, supplied context and each selected answer.

## Try it locally

Extraction and export use no model API. Install [uv](https://docs.astral.sh/uv/) and use Python 3.12:

```sh
git clone https://github.com/wcook04/code-ontology-bridge.git
cd code-ontology-bridge
uv sync --locked
mkdir -p build
uv run cob build code_ontology_bridge --out build/codemap.json --summary build/summary.json
uv run cob export-duckdb --codemap build/codemap.json --out build/repository.duckdb
uv run cob export-model --codemap build/codemap.json --out build/repository.model.yaml --database repository
```

This maps the bridge's own package and produces a summary, a queryable DuckDB file and model YAML. Replace `code_ontology_bridge` with another Python source directory to try a different input. The extractor is a static-analysis prototype. Repeated qualified definitions receive line-qualified IDs; ambiguous call targets remain unresolved. See [known limitations](GAPS.md#source-analysis-limits).

For the recorded NVIDIA example, use the [pinned reproduction guide](docs/reproduction.md). It separates rebuilding data, testing compatibility and running a live model service.

## Find your way around

| Location | Responsibility |
| --- | --- |
| [code_ontology_bridge/](code_ontology_bridge/) | Installable extractor, exporters and governance commands. |
| [eval/](eval/) | Authored evaluation questions and example SQL analyses. |
| [examples/auto-ontology/](examples/auto-ontology/) | Exported dataset and snapshot summary. Its [live/](examples/auto-ontology/live/RESULTS.md) directory holds replay tools, saved runs and the upstream patch. |
| [docs/](docs/README.md) | Case study, reproduction and governance guides. |
| [tests/](tests/) | Local behavior and optional upstream compatibility tests. |
| [tools/](tools/) | Repository checks and paper build command. |
| [SPEC.md](SPEC.md) / [GAPS.md](GAPS.md) | Interface specification / capability status and remaining defects. |

The analysis is static. Callback references may never execute, dynamic calls can be missed, and test links describe imports or matching filenames rather than measured coverage. Missing docstrings remain empty. These limits apply to every answer derived from the map.

Run `uv run pytest -q -ra` and `uv run python tools/check_repository.py` to check the checkout. See [contributing](CONTRIBUTING.md) for optional integration tests and evidence-preservation rules.

## Licence

[Apache License 2.0](LICENSE).

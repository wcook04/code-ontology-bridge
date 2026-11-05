# code-ontology-bridge

code-ontology-bridge turns a Python repository into a DuckDB database and a semantic model for [NVIDIA Auto Ontology](https://github.com/NVIDIA/auto-ontology). Auto Ontology answers questions about the repository through its existing DuckDB connector and native model import, and every answer comes back as SQL and rows with exact file paths and symbol IDs. An optional code semantics layer adds six SQL views that define operations such as direct callers, callback references and shortest call chains.

[Follow a recorded question](https://wcook04.github.io/code-ontology-bridge/) · [Run it locally](#quickstart) · [Read the study](study/RESULTS.md) · [Read the paper](docs/case-study.md)

<a id="one-question-all-the-way-through"></a>

## One recorded question

Which callers have a recorded path to Auto Ontology's `resolve_semantic_fks`, outside tests, and at what shortest depth?

Auto Ontology, querying a map of its own source, returned four callers. Three reach the resolver through direct calls. The fourth, `SemanticScheduler._run_once`, reaches it because the scheduler passes the compilation wrapper to `asyncio.to_thread` at line 203:

```python
tables_processed = await asyncio.to_thread(
    run_semantic_compilation, database_name
)
```

The extractor records that line in `code.calls` as a callback reference: a function passed as an argument, to be run by the receiving call.

![Recorded paths from the compiler, wrapper, scheduler and CLI entry to the foreign-key resolver. The dashed edge is the scheduler's callback reference.](docs/figures/caller-chain.png)

| Caller | Shortest recorded depth | Reached through direct calls only |
| --- | ---: | --- |
| `_run_semantic_compilation` | 1 | Yes |
| `run_semantic_compilation` | 2 | Yes |
| `main` | 3 | Yes |
| `SemanticScheduler._run_once` | 3 | No |

The four callers and their depths are Auto Ontology's saved answer, with the question and generated SQL, in [ask_q11.json](examples/auto-ontology/live/current/responses/10i_ask_with_key/ask_q11.json). The last column comes from a traversal of the same saved data. The request named its output fields and asked the agent to follow calls backwards including callback references. These are static source relationships, recorded from the code as written.

## Quickstart

Extraction, export and SQL queries need no model credentials. Install [uv](https://docs.astral.sh/uv/) and use Python 3.12:

```sh
git clone https://github.com/wcook04/code-ontology-bridge.git
cd code-ontology-bridge
uv sync --locked
mkdir -p build
uv run cob build code_ontology_bridge --out build/codemap.json --summary build/summary.json
uv run cob export-duckdb --codemap build/codemap.json --out build/repository.duckdb
uv run cob export-model --codemap build/codemap.json --out build/repository.model.yaml --database repository
uv run cob semantics --duckdb build/repository.duckdb --model build/repository.model.yaml --out-model build/repository.semantic.model.yaml
```

This maps the bridge's own package; replace `code_ontology_bridge` with another Python source directory to map that instead. Then ask which functions reach `summarise`, the step that counts a code map's rows:

```sh
uv run python - <<'PY'
import duckdb

with duckdb.connect("build/repository.duckdb", read_only=True) as db:
    rows = db.execute("""
        SELECT caller_symbol_id, direct_depth, any_depth
        FROM code.reachability
        WHERE target_symbol_id = 'codemap/builder.py::summarise'
        ORDER BY any_depth, caller_symbol_id
    """).fetchall()
for caller, direct, any_ in rows:
    print(f"{any_}  {'-' if direct is None else direct}  {caller}")
PY
```

The first column is the shortest chain counting callback references, the second the shortest chain of direct calls only. `cli.py::build_parser` and `cli.py::main` show a dash in the second column: `build_parser` registers each `cmd_*` handler as a callback (`set_defaults(func=cmd_build)`), so they reach `summarise` only through those references.

<a id="build-the-exports-locally"></a>

The [reproduction guide](docs/reproduction.md) rebuilds the pinned NVIDIA example and runs the live integration, which needs credentials and the compatibility patch.

## What the bridge supplies

![The bridge exports source rows to DuckDB and definitions to model YAML. Auto Ontology imports the definitions and queries the rows through its existing connector.](docs/figures/architecture.png)

| Export | Contents |
| --- | --- |
| DuckDB database | Eight tables and two views: files, symbols, call sites, imports, class bases, docstrings, static test links and the snapshot's identity. Primary and foreign keys are declared. |
| Base model YAML | Every table and column described, with keys and joins, in Auto Ontology's native import format. At the pinned revision Auto Ontology's DuckDB connector reports no keys (`get_pks` and `get_fks` return empty), so the model declares them. |
| Semantics layer | Six views with their definitions, keys and joins: `call_edges`, `reachability`, `symbol_profile`, `file_profile`, `file_dependencies` and `class_ancestry`. |
| Evaluation dataset | DDL, CSV data and reference questions in NVIDIA's evaluation format. |

The database supplies facts; the model explains them; the layer defines operations on them. A function is a row in `code.symbols`, and the model's terms describe the tables, so the model stays small for any repository size. [`tests/semantics/`](tests/semantics/) checks every view against an independent Python computation on random code maps with cycles. See the [interface specification](SPEC.md) and the [layer](code_ontology_bridge/semantics/layer.py).

## The study

Four repositories (NVIDIA Auto Ontology, click, httpx and rich) and 48 questions, written by separate AI authors who saw the source and a bare database and never the semantics layer, with every answer re-derived by a second AI annotator. The questions, reference SQL and protocol were frozen and pushed before any model ran ([protocol](study/PROTOCOL.md)). An answer is **robust** when its SQL returns the reference rows on the repository's database and on eight altered copies of it (extra calls, callbacks, classes, same-named functions, removed edges).

After the runs, an outside review found a reference query that ignores its question's "functions or methods" restriction. An audit of all 48 found 21 references that miss a restriction their question states and 5 questions with two valid readings; the corrected references were committed before rescoring, the saved responses were rescored without new model calls, and the original scores stay published ([what changed](study/PROTOCOL.md#corrections-after-the-runs)). Corrected robust scores:

A model asked directly, all 48 questions, mean of five runs:

| The model is given | DeepSeek v4.1 Flash | Nemotron 3.5 Lightning |
| --- | ---: | ---: |
| Schema only | 18.0 | 2.4 |
| + base model (descriptions, keys, joins) | **27.2** | 5.4 |
| + semantics layer (views and definitions) | 26.8 | **7.6** |

Inside NVIDIA Auto Ontology's own agent, the 12 Auto Ontology questions, mean of three runs:

| Auto Ontology is given | DeepSeek v4.1 Flash | Nemotron 3.5 Lightning |
| --- | ---: | ---: |
| Nothing imported (its own catalog) | 10.3 | 0.7 |
| + base model | 8.7 | 2.3 |
| + semantics layer views and model | **10.7** | 2.3 |

Asked directly, the exported model lifts DeepSeek by about 9 robust answers (9 questions improve, 1 regresses), and the semantics layer is the best briefing for Nemotron (6 improve, none regress against the schema alone). Inside Auto Ontology, DeepSeek with Auto Ontology's own catalog already answers most questions; the semantics layer gives DeepSeek's highest mean, within run-to-run variation of the native catalog, while the base model alone scores lower; for Nemotron both imports raise the native 0.7 to 2.3. Every number, question and response, and the frozen scores, are in [study/RESULTS.md](study/RESULTS.md).

| Evidence | What it is |
| --- | --- |
| [The study](study/) | 48 questions across four repositories, five direct runs and three Auto Ontology runs per configuration, robust scoring. The current evidence. |
| [Earlier comparison](examples/auto-ontology/live/RESULTS.md) | 38 questions about Auto Ontology written by this project's author, one run per arm. Kept as history; [its protocol](docs/experiment-protocol.md). |
| [Recorded walkthrough](examples/auto-ontology/live/current/) | The 22-question development run inside Auto Ontology, including the question above; the website follows it. |

## Limits

The questions were written by AI authors under the protocol's rules, not by the repositories' maintainers, and the Auto Ontology comparison has 12 questions. Reference answers are correct for the extracted database; the extractor is static, so it misses dynamic calls and calls through local aliases or package re-exports, and test links are associations, not coverage ([source-analysis limits](GAPS.md#source-analysis-limits)). Nemotron scores low on these questions throughout.

## Integration compatibility

| Task | Requirements |
| --- | --- |
| Extract source, export and query the database, export model YAML | This package alone, with DuckDB and PyYAML. |
| Reproduce the recorded Auto Ontology runs | Auto Ontology at [`cdaf61e`](https://github.com/NVIDIA/auto-ontology/tree/cdaf61e1bd0cf3820d11d72b43bb460816aebbd3) with the [twelve-file compatibility patch](examples/auto-ontology/live/upstream-fix/README.md), PostgreSQL and model credentials. The patch selects public model clients, forwards the SQL-only route through chat and tightens response validation. |
| Use a current Auto Ontology revision | Untested. The exports use the existing connector and native model format; which patch changes are still needed has to be checked against that revision. |

<a id="serve-data-for-a-website"></a>

## Inspect the saved evidence

`cob inspect-export`, `cob inspect-publish` and `cob inspect-serve` build a bundle, a static publication and a read-only local API over the committed example and the recorded walkthrough, with no model credentials. See the [inspection API](docs/inspection-api.md). Separate [governance commands](docs/governance.md) record checks and annotate SQL.

The source-map approach comes from **CodeMap**, Will Cook's earlier source-navigation tool, adapted here into a standalone extractor.

## Find your way around

| Location | Contents |
| --- | --- |
| [code_ontology_bridge/](code_ontology_bridge/) | Extractor, exporters, semantics layer, inspection API and governance commands. |
| [study/](study/) | The study: protocol, questions, reference corrections, runners, every response and scores. |
| [examples/auto-ontology/](examples/auto-ontology/) | The generated Auto Ontology dataset, the live runner, the compatibility patch and the earlier runs. |
| [docs/](docs/README.md) | Paper, PDF, figures and task guides. |
| [eval/](eval/) | Questions and contracts of the earlier comparison. |
| [site/](site/README.md) | The reading website. |
| [tests/](tests/) | Package tests and optional upstream compatibility checks. |
| [tools/](tools/) | Repository checks, paper builder and [publication tools](docs/deployment.md). |
| [SPEC.md](SPEC.md) / [GAPS.md](GAPS.md) | Interface contract / current limits and remaining work. |

Run `uv run pytest -q -ra` and `uv run python tools/check_repository.py` to check a checkout. See [contributing](CONTRIBUTING.md).

## Licence

[Apache License 2.0](LICENSE). An independent integration with NVIDIA's open-source project, by Will Cook.

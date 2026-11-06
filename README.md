# code-ontology-bridge

code-ontology-bridge lets [NVIDIA Auto Ontology](https://github.com/NVIDIA/auto-ontology) answer questions about a Python codebase, such as "if this function changed, which other functions would be affected?". It reads the source code and writes a database of its files, functions, classes, calls and imports. Auto Ontology's agent then answers by writing SQL against that database, so every answer arrives with the query that produced it and rows that name exact files and functions, and a person can check it.

[See one question answered, step by step](https://wcook04.github.io/code-ontology-bridge/) · [Results](#results) · [Run it locally](#quickstart) · [Paper (PDF)](docs/case-study.pdf)

## How it works

```
Python source  →  cob (this package)  →  code database + table descriptions  →  Auto Ontology  →  answer: SQL + rows
```

| Piece | What it is | How Auto Ontology uses it |
| --- | --- | --- |
| **Code database** | A DuckDB file with 8 tables and 2 views: files, functions and classes, every call between them, imports, base classes, docstrings and test files. Every table has a declared primary key; foreign keys link calls to the functions they connect. | Connected through Auto Ontology's existing DuckDB connector, unmodified. |
| **Table descriptions** | A semantic model in Auto Ontology's own import format: what every table and column means, each table's key, and how the tables join. It describes tables, so its size does not grow with the codebase. | Loaded through Auto Ontology's existing model import (`POST /api/model/import`), unmodified. |
| **Ready-made queries** (optional) | Six SQL views over the code database, with their descriptions: direct calls and callbacks between each pair of functions, every function that can reach another and by how many calls, per-function and per-file summaries, which files import which, and class inheritance. In the code they are called the semantics layer. | Added to the database and described in the imported model, so the agent can select from them instead of writing recursive SQL. |

Auto Ontology's DuckDB connector at the tested revision reports no primary or foreign keys (`get_pks` and `get_fks` return empty tables), so the table descriptions also carry the keys and joins. The ready-made queries are tested against a separate Python implementation on randomly generated codebases, including ones where functions call each other in a loop ([tests](tests/semantics/)).

<a id="one-question-all-the-way-through"></a>

## One question, answered

> If `resolve_semantic_fks` changed, which other functions in Auto Ontology would be affected, and through how many calls?

`resolve_semantic_fks` is the Auto Ontology function that resolves foreign keys (links between tables). Asked about a code database of its own source, Auto Ontology's agent returned four functions:

| Function | Calls between it and `resolve_semantic_fks` | How it gets there |
| --- | ---: | --- |
| `_run_semantic_compilation` | 1 | Calls it directly. |
| `run_semantic_compilation` | 2 | Calls `_run_semantic_compilation`. |
| `main` | 3 | Calls `run_semantic_compilation`. |
| `SemanticScheduler._run_once` | 3 | Hands `run_semantic_compilation` to `asyncio.to_thread`, which runs it. |

The fourth one never calls the chain by name. At line 203 of the scheduler it passes the function as an argument:

```python
tables_processed = await asyncio.to_thread(
    run_semantic_compilation, database_name
)
```

A text search for calls written as `run_semantic_compilation(` finds `main` and misses the scheduler, because the scheduler never writes the brackets. The extractor records this line as a **callback**: a function passed to another call that will run it. That row is what lets a database query find the scheduler.

![Arrows from four calling functions to resolve_semantic_fks. The scheduler's arrow is dashed because it passes the function as an argument.](docs/figures/caller-chain.png)

The request told the agent to follow calls backwards and to include callbacks, so the agent did not discover that method. What the example shows is that the callback exists as a row the agent can query. The saved answer, with the full request and the SQL the agent wrote, is [ask_q11.json](examples/auto-ontology/live/current/responses/10i_ask_with_key/ask_q11.json). This example comes from the development run, whose questions the author wrote; the blind study is below.

## Results

**Given only the code database, with nothing imported, Auto Ontology's agent with DeepSeek v4.1 Flash answered 10.3 of 12 code questions correctly** (mean of three runs; 11.7 of 12 on the unaltered database). **Asked directly, outside Auto Ontology, the same model answered 27.2 of 48 correctly with the table descriptions, against 18.0 with table names alone.**

An answer counts as **correct** only if its SQL returns the right rows on the real code database and on eight altered copies of it. The copies add calls, callbacks, classes and functions with duplicate names, and remove some calls, so a query that matches the right rows by luck on one database fails. The 48 questions cover four open-source Python codebases: Auto Ontology, click, httpx and rich. Separate AI models wrote them, with the correct answers, from the source code and the bare code database, without seeing the table descriptions or the ready-made queries. A second AI model re-derived every answer from the question wording as a check on the answer key. Everything was published before any test ran ([protocol](study/PROTOCOL.md)).

**Asked directly** (all 48 questions, mean of five runs, correct answers):

| The model is given | DeepSeek v4.1 Flash | Nemotron 3.5 Lightning |
| --- | ---: | ---: |
| Table names only | 18.0 | 2.4 |
| + table descriptions | **27.2** | 5.4 |
| + ready-made queries, without descriptions | 25.4 | 2.8 |
| + table descriptions and ready-made queries | 26.8 | **7.6** |

With the table descriptions, DeepSeek answers 9 questions better and 1 worse than with table names alone. Nemotron does best with the descriptions and ready-made queries together: 6 questions better, none worse.

**Inside Auto Ontology** (the 12 questions about Auto Ontology's own code, mean of three runs, correct answers; every row queries the same code database):

| Auto Ontology is given | DeepSeek v4.1 Flash | Nemotron 3.5 Lightning |
| --- | ---: | ---: |
| The code database, nothing imported | 10.3 | 0.7 |
| + table descriptions | 8.7 | 2.3 |
| + table descriptions and ready-made queries | 10.7 | 2.3 |

Inside Auto Ontology, importing the descriptions did not measurably help DeepSeek: 10.3 against 10.7 is smaller than the spread between repeat runs (10 to 11 against 10 to 12), and the descriptions alone scored lower. For Nemotron both imports raised the score from 0.7 to 2.3. Nemotron scored low throughout. It ran at temperature 0 with reasoning switched off, and most of its failures are queries that run but return the wrong rows.

The answer keys were corrected after the runs. An outside reviewer found that one answer key ignored its question's "functions or methods" condition; four further AI auditors, who did not see any scores, then found 21 answer keys that missed a condition their question states, and 5 questions that can be read two ways. The corrections were published before rescoring, no model was asked again, and the original scores stay published ([what changed](study/PROTOCOL.md#corrections-after-the-runs)). Every question, answer key, saved answer and score is in [study/RESULTS.md](study/RESULTS.md).

## Quickstart

Building the code database and querying it needs no model and no credentials. Install [uv](https://docs.astral.sh/uv/) and use Python 3.12:

```sh
git clone https://github.com/wcook04/code-ontology-bridge.git
cd code-ontology-bridge
uv sync --locked
mkdir -p build
uv run cob build code_ontology_bridge --out build/codemap.json --summary build/summary.json
uv run cob export-duckdb --codemap build/codemap.json --out build/repository.duckdb
uv run cob export-model --codemap build/codemap.json --out build/repository.model.yaml --database repository
uv run cob semantics --duckdb build/repository.duckdb --model build/repository.model.yaml --out-model build/repository.with-queries.model.yaml
```

These commands map this package's own source. The third writes the code database, the fourth the table descriptions, and the fifth adds the ready-made queries to the database and writes a second model that also describes them. To map another codebase, replace `code_ontology_bridge` with its source folder.

Then ask which functions lead to `summarise`, the function that counts the rows in a code map:

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

Each line shows the fewest calls from that function to `summarise` counting callbacks, then the fewest through direct calls only, then the function. `cli.py::build_parser` and `cli.py::main` show a dash in the second column: `build_parser` registers each `cmd_*` command function as a callback (`set_defaults(func=cmd_build)`), so they reach `summarise` only through callbacks.

<a id="build-the-exports-locally"></a>

To load these files into a running Auto Ontology, follow the [reproduction guide](docs/reproduction.md). It needs PostgreSQL, model credentials and the compatibility patch described below.

## Compatibility with Auto Ontology

| Task | What it needs |
| --- | --- |
| Build and query the code database, write the table descriptions | This package alone (DuckDB and PyYAML). |
| Reproduce the recorded Auto Ontology runs | Auto Ontology at [`cdaf61e`](https://github.com/NVIDIA/auto-ontology/tree/cdaf61e1bd0cf3820d11d72b43bb460816aebbd3) (3 November 2026) with the [compatibility patch](examples/auto-ontology/live/upstream-fix/README.md), PostgreSQL and model credentials. |
| Use the current Auto Ontology `main` | Untested. |

The DuckDB connector and the model import ran unmodified. The patch, twelve file diffs including tests, changes three things that the recorded runs needed: it lets each model role use any OpenAI-compatible service (the runs used OpenRouter), it passes Auto Ontology's existing SQL-only option through the chat API so code questions go to the SQL pipeline, and it extends an existing check that rejects placeholder text such as "TODO" in answers.

## Limits

- The questions were written by AI models under the protocol's rules, not by the codebases' maintainers. Inside Auto Ontology there are 12 questions.
- The answer keys are correct for the code database. The extractor reads source text, so it misses calls made dynamically, calls through a local alias and names reached through package re-exports, and a recorded callback is not proof that the function runs. Test files are linked to code by imports and file names, which is not test coverage ([all source-analysis limits](GAPS.md#source-analysis-limits)).

## Evidence

| Evidence | What it is |
| --- | --- |
| [The study](study/) | The 48 questions above, every saved answer and score, and the protocol. The current evidence. |
| [Recorded walkthrough](examples/auto-ontology/live/current/) | The 22-question development run inside Auto Ontology, with author-written questions, including the example above. The website follows it. |
| [Earlier comparison](examples/auto-ontology/live/RESULTS.md) | 38 author-written questions about Auto Ontology, one run per setting. Kept as history, with [its protocol](docs/experiment-protocol.md). |

<a id="serve-data-for-a-website"></a>

The commands `cob inspect-export`, `cob inspect-publish` and `cob inspect-serve` build a read-only local API and a static copy of the recorded walkthrough for browsing, with no model credentials ([inspection API](docs/inspection-api.md)). Separate [governance commands](docs/governance.md) record which descriptions a person has approved and annotate a generated SQL query with the descriptions it appears to rely on.

## Find your way around

| Folder | What it holds |
| --- | --- |
| [code_ontology_bridge/](code_ontology_bridge/) | The extractor, the database and description exporters, the ready-made queries, the inspection API and the governance commands. |
| [study/](study/) | The study: protocol, questions, answer-key corrections, runners, every saved answer and scores. |
| [examples/auto-ontology/](examples/auto-ontology/) | The code database of Auto Ontology, the live runner, the compatibility patch and the earlier runs. |
| [docs/](docs/README.md) | The paper, figures and task guides. |
| [eval/](eval/) | Questions of the earlier comparison. |
| [site/](site/README.md) | The reading website. |
| [tests/](tests/) | Package tests and optional tests against an Auto Ontology checkout. |
| [tools/](tools/) | Repository layout rules, the paper builder and [publication tools](docs/deployment.md). |
| [SPEC.md](SPEC.md) / [GAPS.md](GAPS.md) | The interface specification / current limits and remaining work. |

Run `uv run pytest -q -ra` for the tests and `uv run python tools/check_repository.py` for the layout rules. See [contributing](CONTRIBUTING.md) and the [paper's source](docs/case-study.md).

## Credits and licence

By Will Cook. The extractor adapts the source map from CodeMap, his earlier tool for navigating source code. [Apache License 2.0](LICENSE). This is an independent integration with NVIDIA's open-source project and is not affiliated with or endorsed by NVIDIA.

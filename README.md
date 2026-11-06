# code-ontology-bridge

A program is made of functions that call one another, and questions such as "if this function changed, which other functions would be affected?" are slow to answer by reading files. code-ontology-bridge reads Python source code and writes a database of its files, functions, classes, calls and imports, so that [NVIDIA Auto Ontology](https://github.com/NVIDIA/auto-ontology), NVIDIA's open-source system for answering questions about databases, can answer such questions. Auto Ontology's agent, an AI model that writes database queries, answers in SQL, so every answer arrives with the query that produced it and rows naming exact files and functions, and a person can check it.

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

| Function | Steps to `resolve_semantic_fks` (calls or hand-overs) | How it gets there |
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

The extractor records this line as a **callback**: a function handed to another call that will run it. Because callbacks are rows of their own, one recursive query can follow the chain across three files, distinguish a call from a hand-over and report the number of steps. A text search finds the name but cannot tell a call from a hand-over or follow the chain.

![Arrows from four calling functions to resolve_semantic_fks. The scheduler's arrow is dashed because it passes the function as an argument.](docs/figures/caller-chain.png)

In the figure, Compiler is `_run_semantic_compilation`, Wrapper is `run_semantic_compilation`, Scheduler is `SemanticScheduler._run_once`, CLI entry is `main`, and FK resolver is `resolve_semantic_fks`.

The request told the agent to follow calls backwards and to include callbacks, so the agent did not discover that method. What the example shows is that the callback exists as a row the agent can query. The saved answer, with the full request and the SQL the agent wrote, is [ask_q11.json](examples/auto-ontology/live/current/responses/10i_ask_with_key/ask_q11.json). This question comes from the earlier experiment, whose questions the author wrote.

A question from the blind study below, written by someone else, asked which functions Auto Ontology's query pipeline hands over to be run later (`ao-02`). Auto Ontology's agent, given only the code database, answered it correctly in all 3 runs. The same model asked directly, without Auto Ontology, answered it correctly in none of 5 runs given the table names or the table descriptions, and in 1 of 5 given the descriptions and ready-made queries.

## Results

The study asked 48 questions about four open-source Python codebases: Auto Ontology, click, httpx and rich. An answer counts as **correct** when its SQL returns the right rows on all of these:

- the real code database;
- eight altered copies of it, which add calls, callbacks, classes and functions with duplicate names and remove some calls, so that a query matching the right rows by luck fails.

Separate AI models wrote the questions and their answer keys from the source code and the bare code database, without seeing the table descriptions or the ready-made queries. A second AI model re-derived every answer from the question wording; on the real databases all 48 matched. Everything was published before any test ran ([protocol](study/PROTOCOL.md)).

**Inside Auto Ontology, with only the code database connected, the agent with DeepSeek v4.1 Flash answered 10.3 of the 12 questions about Auto Ontology's own code correctly** (mean of three runs), Auto Ontology building its own description of the database. Asked the same 12 questions directly, outside Auto Ontology, DeepSeek answered 3.2 correctly, or 4.4 with the table descriptions. Auto Ontology's agent adds retrieval and repair of failed queries and ran with the provider's default reasoning setting, so this compares the two whole setups.

**Asked directly, the table descriptions lift DeepSeek from 18.0 to 27.2 of all 48 questions** (mean of five runs); counting only the real database, from 28.6 to 41.6. With the descriptions, 9 questions improve and 1 gets worse.

After the runs, an outside reviewer found that one answer key ignored its question's "functions or methods" condition. Four further AI auditors, who saw no scores, found that 21 of the 48 answer keys missed a condition their question states, and that 5 of the 48 questions can be read two ways. Both checks above had matched on the real databases; the missing conditions only change results on the altered copies. The corrections were published before rescoring and no model was asked again. They raised Auto Ontology's 10.3 from 7.3 and lowered the direct result with descriptions from 34.0 to 27.2; the original scores stay published ([what changed](study/PROTOCOL.md#corrections-after-the-runs)).

**Asked directly** (all 48 questions, correct answers, mean of five runs). Each row gives the model more information about the database:

| The model is given | DeepSeek v4.1 Flash | NVIDIA Nemotron 3.5 Lightning |
| --- | ---: | ---: |
| Table names only | 18.0 | 2.4 |
| + table descriptions | **27.2** | 5.4 |
| + ready-made queries, without descriptions | 25.4 | 2.8 |
| + table descriptions and ready-made queries | 26.8 | **7.6** |

**Inside Auto Ontology** (the 12 Auto Ontology questions, correct answers, mean of three runs). Every row queries the same code database; the rows differ in what is imported on top:

| Auto Ontology is given | DeepSeek v4.1 Flash | NVIDIA Nemotron 3.5 Lightning |
| --- | ---: | ---: |
| The code database, nothing imported | 10.3 | 0.7 |
| + table descriptions | 8.7 | 2.3 |
| + table descriptions and ready-made queries | 10.7 | 2.3 |

For DeepSeek inside Auto Ontology, the table descriptions alone scored lower than nothing imported (8.7 against 10.3; runs ranged 8 to 9 against 10 to 11), and adding the ready-made queries gave 10.7, within the spread between runs. For Nemotron both imports raised the score from 0.7 to 2.3.

Nemotron, NVIDIA's own model and the default model family in Auto Ontology's configuration, scored low throughout. Asked directly it ran at temperature 0 with reasoning switched off; inside Auto Ontology it used the provider's default. Most of its failures are queries that run but return the wrong rows. Every question, answer key, saved answer and score is in [study/RESULTS.md](study/RESULTS.md).

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

These commands map this package's own source. `cob build` reads the source, `cob export-duckdb` writes the code database, `cob export-model` writes the table descriptions, and `cob semantics` adds the ready-made queries to the database and writes a second set of descriptions that also covers them. To map another codebase, replace `code_ontology_bridge` with its source folder.

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

### Load it into Auto Ontology

[`run_live.sh`](examples/auto-ontology/live/run_live.sh) does these three steps against a local Auto Ontology; the [reproduction guide](docs/reproduction.md) lists what it needs (PostgreSQL, model credentials and the compatibility patch described below).

1. Start Auto Ontology's ingestion service with `CONNECTION_STRINGS=duckdb:///<absolute path>/repository.duckdb`, so it catalogs the code database through its DuckDB connector.
2. Rewrite the table descriptions' catalog IDs to the IDs the server gave those tables ([`remap_catalog_ids.py`](examples/auto-ontology/live/remap_catalog_ids.py)). Without this step the import tries to create the tables a second time and fails on Auto Ontology's unique-name constraints.
3. Send the YAML to `POST /api/model/import?replace=false` with content type `application/x-yaml`.

## Compatibility with Auto Ontology

| Task | What it needs |
| --- | --- |
| Build and query the code database, write the table descriptions | This package alone (DuckDB and PyYAML). |
| Reproduce the recorded Auto Ontology runs | Auto Ontology at [`cdaf61e`](https://github.com/NVIDIA/auto-ontology/tree/cdaf61e1bd0cf3820d11d72b43bb460816aebbd3) (3 November 2026) with the [compatibility patch](examples/auto-ontology/live/upstream-fix/README.md), PostgreSQL and model credentials. |
| Use the current Auto Ontology `main` | Untested. |

The DuckDB connector and the model import ran unmodified. The patch, twelve file diffs including tests, changes three things that the recorded runs needed: it lets each model role use any OpenAI-compatible service (the runs used OpenRouter), it passes Auto Ontology's existing SQL-only option through the chat API so code questions go to the SQL pipeline, and it extends an existing check that rejects placeholder text such as "TODO" in answers.

## Limits

- The questions were written by AI models under the protocol's rules, not by the codebases' maintainers. Inside Auto Ontology there are 12 questions, and all runs used Auto Ontology at `cdaf61e`.
- The answer keys are correct for the code database. The extractor reads source text, so it misses calls made dynamically, calls through a local alias and names reached through package re-exports, and a recorded callback is not proof that the function runs. Test files are linked to code by imports and file names, which is not test coverage ([all source-analysis limits](GAPS.md#source-analysis-limits)).

## Evidence

| Evidence | What it is |
| --- | --- |
| [The study](study/) | The 48 questions above, every saved answer and score, and the protocol. The current evidence. |
| [Earlier experiment](examples/auto-ontology/live/RESULTS.md) | 38 author-written questions about Auto Ontology, 22 for development and 16 held out, one run per setting. Kept as history, with [its protocol](docs/experiment-protocol.md). The example above and the website's walkthrough come from [its recorded development run](examples/auto-ontology/live/current/). |

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

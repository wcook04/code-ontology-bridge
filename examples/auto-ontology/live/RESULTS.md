# What the semantic model and Auto Ontology each add: 4 November 2026

The same language model answered the same questions about Auto Ontology's own code three ways, under a [protocol](../../../docs/experiment-protocol.md) committed before any run:

- **A, schema only.** The model sees the tables' and columns' names and types, writes SQL, and may try again after an SQL error (three runs at most).
- **B, schema plus the exported semantic model.** The same, plus what this project's semantic model says: each table's and column's description, the primary keys and the 10 declared joins.
- **C, Auto Ontology.** Auto Ontology imports the semantic model, and its agent retrieves context, writes the SQL, checks it and repairs it, querying the database through its DuckDB connector.

Two models, two question sets, eleven complete runs: Nemotron has no held-out result inside Auto Ontology (below). Each run asked every question once; no question was asked again.

## Questions with exactly the expected rows

| Model | Arm | Development (22, 18 with hints) | Held-out (16, no hints) |
| --- | --- | ---: | ---: |
| NVIDIA Nemotron 3.5 Lightning | A, schema only | 10 | 6 |
| | B, + semantic model | 13 | 13 |
| | C, Auto Ontology | 12 | no result |
| DeepSeek v4.1 Flash | A, schema only | 14 | 13 |
| | B, + semantic model | 18 | 16 |
| | C, Auto Ontology | **22** | 14 |

**B minus A is what the exported semantic model is worth by itself.** Every model and question set improves: Nemotron goes from 6 to 13 of 16 held-out questions, DeepSeek from 13 to 16.

**C minus B is what Auto Ontology adds on top of the same metadata.** Nemotron's one complete Auto Ontology run scored 12 of 22 development questions, against 13 with the metadata in the prompt; it ran through Auto Ontology's OpenAI-compatible client, which cannot switch off Nemotron's reasoning, so 1,120 of its structured-output calls used up the 8,192-token output limit and several answers came back empty. Its held-out run and three repeats through Auto Ontology's NVIDIA client with reasoning off were rate-limited by the NVIDIA API and are discarded, so Nemotron has no held-out result inside Auto Ontology. On the development set, DeepSeek inside Auto Ontology returned the expected rows for all 22 questions, against 18 with the metadata in the prompt. On the held-out set it scored 14 against 16. Its two misses:

- **Q101** asks which "functions or methods" `run_ingest` calls directly. Auto Ontology's SQL keeps only callees whose kind is function or method, which drops the one callee that is a class (a constructor call); the reference counts it. The question's wording supports both readings.
- **Q106** asks for public functions with no recorded caller. Auto Ontology's SQL also admits methods and returns one extra row.

The held-out set is 16 questions, and each arm ran once, so a difference of one or two questions is within what a second run could change.

## How each arm worked

| Model | Arm | Set | Median seconds per request | Requests that needed a repair |
| --- | --- | --- | ---: | ---: |
| Nemotron 3.5 Lightning | A, schema only | development | 29.4 | 2 |
| Nemotron 3.5 Lightning | A, schema only | held-out | 28.9 | 2 |
| Nemotron 3.5 Lightning | B, + semantic model | development | 16.4 | 4 |
| Nemotron 3.5 Lightning | B, + semantic model | held-out | 20.9 | 2 |
| Nemotron 3.5 Lightning | C, Auto Ontology | development | 706.5 | 3 |
| DeepSeek v4.1 Flash | A, schema only | development | 3.6 | 0 |
| DeepSeek v4.1 Flash | A, schema only | held-out | 6.7 | 1 |
| DeepSeek v4.1 Flash | B, + semantic model | development | 2.5 | 0 |
| DeepSeek v4.1 Flash | B, + semantic model | held-out | 2.5 | 0 |
| DeepSeek v4.1 Flash | C, Auto Ontology | development | 175.1 | 13 |
| DeepSeek v4.1 Flash | C, Auto Ontology | held-out | 158.9 | 9 |

Arms A and B called the model directly at temperature 0. Their manifests record the model, endpoint and inputs but not a commit; they started at 21:44:04 UTC, when the checkout was at `2d3686c`. The DeepSeek Auto Ontology runs record `e1d41b3`, which changed only the website and the summariser. Arm C ran three requests at a time. The two models' Auto Ontology runs shared one laptop, on separate ports, so its times include that contention. The NVIDIA API served Nemotron and OpenRouter served DeepSeek; Auto Ontology used NVIDIA's `nemotron-3-embed-1b` and `llama-nemotron-rerank-vl-1b-v2` for retrieval in every C run.

In the DeepSeek development run inside Auto Ontology, twelve of the 22 first queries named a table without its `code.` schema (for example `FROM calls`) and failed with a DuckDB catalog error. Auto Ontology's repair step read the error, added the schema and ran the query again; all twelve then returned the expected rows. Question 2's rows are right, but its written explanation is the single word "Purple": that request reached Auto Ontology's "unconstructable SQL" step, started again from the beginning, and returned that text with the correct SQL.

## The recorded example on the website

The website follows the DeepSeek development run inside Auto Ontology question by question: [`current/`](current/) holds its manifest, frozen inputs, every response and the service logs, with [artifacts.json](current/artifacts.json) listing each file's SHA-256. The manifest binds the run to the exact database it queried (`dataset_sha256`, algorithm `cob_typed_tables_v1`) and to the runner files, unchanged from start to finish.

Every run of all three arms is in [`experiment/`](experiment/), one folder per model, arm and question set, with its responses, manifest and score; [summary.json](experiment/summary.json) collects the numbers above and each question's result in each run.

## What was fixed before these runs

- **Extractor.** Imports bind only in the function, method or class that contains them, and calls inside a nested function count for the enclosing function only when it calls or passes on that nested function. Rebuilding the database with these fixes removed 21 of 9,442 linked calls and added 7; the four question 11 callers did not change. Regression tests are in `tests/codemap/test_scopes.py`.
- **Reference queries.** Question 11's reference no longer stops at depth 6, and question 20's groups by directory. `tests/export/test_reference_semantics.py` checks the question 11 reference on a synthetic repository with a seven-deep chain, a cycle and two paths to one caller.
- **Instructions.** The shared instruction no longer asks the agent to describe the returned rows: Auto Ontology writes its explanation before the query runs and returns the rows beside it.
- **Held-out questions.** Sixteen questions without hints, with their reference queries, were committed before any arm ran.
- **Dry run.** With each reference query in place of the model, the harness scored 22 of 22 and 16 of 16, which checks the scoring, not any model.

## Discarded runs

Seven attempts were discarded whole, as the protocol requires; [experiment/discarded.txt](experiment/discarded.txt) lists each with its reason.

- The first four Auto Ontology attempts never started PostgreSQL: the run folder's path made its Unix socket path longer than the 103-byte limit. No question was asked.
- The next set stopped when the laptop shut down partway through; every run was started again from the first question.
- Four Nemotron Auto Ontology attempts were rate-limited by the NVIDIA API ("429 Too Many Requests"): the first-configuration held-out run and a ChatNVIDIA development run that ran at once on one key, then a ChatNVIDIA development run alone with three requests at a time, then one with a single request at a time. The protocol was amended, and the amendments committed, before the ChatNVIDIA attempts: they route Nemotron through Auto Ontology's NVIDIA client with reasoning off, one request at a time. Even then the key returned about 50 rate-limit errors a minute, so no amended run completed.

## What this does and does not show

It shows that the exported semantic model, on its own, makes two different models write correct SQL over the code database much more often, and that Auto Ontology's agent, given that model, answered every development question correctly with one of them.

It does not show accuracy on questions someone else wrote: the author wrote all 38 questions and their reference queries, about one repository. Each arm ran once. Matching rows on this snapshot does not prove two queries are equivalent on other data. The extractor reads source text, so the rows describe the code's text, not what it does at run time.

## Reproduction

`examples/auto-ontology/live/direct_sql_run.py` runs arms A and B; `fresh_run.py` runs arm C (`fresh_run_lane.py` shifts its local ports so two can share a machine); `evaluate_run.py` scores every arm; `tools/summarise_experiment.py` collects the runs; `tools/promote_run.py` makes one complete run the website's record. The [reproduction guide](../../../docs/reproduction.md) covers building the data and the upstream patch.

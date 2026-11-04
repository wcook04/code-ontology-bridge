# Experiment protocol: what the exported model and Auto Ontology each add

Written and committed before any run of this experiment. Results are reported against it as written; a change to the protocol is a new commit made before the run it affects, and the results page names the protocol commit each run used.

## Question

For questions about a Python code base, how much does each layer contribute to getting the right rows?

- **Arm A, schema only.** One language model writes DuckDB SQL from the physical schema: table names, column names and types.
- **Arm B, schema plus the exported model.** The same model also receives what this project's semantic model says: each table's and column's description, the primary keys and the 10 declared joins. Auto Ontology is not involved.
- **Arm C, Auto Ontology.** The same model, used by Auto Ontology's SQL agent after importing the semantic model into its catalog, with the database queried through its DuckDB connector.

A minus B measures what the exported descriptions and keys are worth on their own. B minus C measures what Auto Ontology's retrieval, validation and repair steps add on top.

## Fixed inputs

- Source analysed: NVIDIA Auto Ontology at `cdaf61e1bd0cf3820d11d72b43bb460816aebbd3`.
- Database and model: `examples/auto-ontology/auto_ontology_code.duckdb` and `auto_ontology_code.model.yaml`, rebuilt by `examples/auto-ontology/reproduce.sh` with the current extractor. The tests require a rebuild to reproduce the committed files exactly.
- Auto Ontology for arm C: the same commit with the twelve-file patch in `examples/auto-ontology/live/upstream-fix/`, needed to use a public model API and the SQL-only chat route.
- Language model: one model for all three arms, recorded in each run's `manifest.json`, with temperature 0 where the arm sets it.

## Question sets

- **Development set**, `eval/auto_ontology_questions.json`, 22 questions written while the project was built. 18 carry a hint. Two reference queries were corrected before this protocol: question 11 no longer stops at depth 6, and question 20 groups by directory. `tests/export/test_reference_semantics.py` runs the question 11 reference on a synthetic repository with a seven-deep chain, a cycle and two paths to one caller.
- **Held-out set**, `eval/heldout_questions.json`, 16 questions written for this protocol before any arm saw them. None has a hint; each names only its output columns. Their reference queries were run once on the database to make sure each returns a definite answer, and were not changed after any arm ran.

Every request sends the question, its hint if it has one, and the output contract with the shared instruction in `eval/answer_contracts.json` (protocol `explicit-output-v4`) or `eval/heldout_contracts.json` (`heldout-v1`).

## Running

- Each arm runs each question set once, completely, with three requests at a time.
- Arms A and B: `examples/auto-ontology/live/direct_sql_run.py`. After an SQL error the model sees the error and may try again, up to three runs in all, which matches the rewrites Auto Ontology's own pipeline makes.
- Arm C: `examples/auto-ontology/live/fresh_run.py`, with `COB_QUESTION_SET=heldout` for the held-out set.
- No single question is rerun. A run stopped by an infrastructure failure (a service that does not start, a provider outage) is discarded whole and repeated; the discarded run is listed with its reason.

## Scoring and reporting

- All arms are scored by `examples/auto-ontology/live/evaluate_run.py`: the returned rows must have the requested columns and types and match the reference rows as a multiset, in order where the contract asks for it.
- Reported per arm and set: questions with exactly the expected rows, SQL runs per question, requests that needed a repair, seconds per request, and model tokens where the provider reports them.
- The written explanation is kept with each response. Auto Ontology writes it before the query runs, so it is not scored against the result.
- Every response of every run is published, with the protocol commit, the model and the input hashes.

## Amendment, 4 November 2026, 23:55 UTC (before the runs it affects)

The Nemotron runs of arm C sent chat through Auto Ontology's OpenAI-compatible client, because `run_live.sh` selects that client whenever `AO_CHAT_ENDPOINT` is set. That client never sends the compatibility patch's Nemotron thinking switch, so Nemotron 3.5 Lightning reasoned by default, and 1,120 of Auto Ontology's structured-output calls in the development run used the whole 8,192-token output limit on reasoning. Those two runs are kept and reported as run.

Two further Nemotron arm C runs, development and held-out, use the route the patch provides for Nemotron: the NVIDIA endpoint through Auto Ontology's ChatNVIDIA client, with reasoning off (`enable_thinking: false`). `fresh_run_lane.py --native-nvidia` drops `AO_CHAT_ENDPOINT` so `run_live.sh` takes that route, and records it in each run's `lane.json`. Every other input, the question sets, the scorer and the one-run rule are unchanged. Arms A and B are not rerun.

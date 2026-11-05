# Study protocol: does a code semantics layer make SQL agents answer code questions correctly?

Committed before any model sees the questions. Results are reported against this file as committed; any change is a new commit made before the runs it affects, and is listed at the end.

## Question

Language models answering questions about a Python code base from a database of its source facts go wrong in recurring ways: a "direct callers" query that keeps callback references, a reachability query that stops at a fixed depth, a "function" count that includes classes, a folder grouping taken from the module name. The code semantics layer (`code_ontology_bridge/semantics/layer.py`) defines those concepts once, as DuckDB views with documented columns, keys, joins and a short glossary, exported in Auto Ontology's native model format.

The study measures how much each part of what the bridge exports contributes to correct answers, on questions written by people who never saw the layer.

## Order of work, fixed by commits

1. The semantics layer and its property tests were committed first (commit `1267519`), before any question existed.
2. Four question authors, one per repository, each wrote 12 questions from the source code and the **base** database only. They were instructed not to open the layer's code, its tests, the study folder or the repository history, and their database copies contained no layer views.
3. A second, independent annotator per repository received only the questions and output contracts (no reference SQL) and wrote their own SQL. Every disagreement was resolved by rewording the question so that one reading remains, or by removing the question; resolutions are recorded in `study/questions/adjudication.md`.
4. This protocol, the final questions and their reference SQL are committed together before any model run.
5. The counterfactual databases are generated from that commit with fixed seeds.

## Data

Four repositories pinned in `study/repos.json`: NVIDIA Auto Ontology (474 Python files), pallets/click (91), encode/httpx (60) and Textualize/rich (213), built by `study/build_data.sh`. Every arm queries the same DuckDB file per repository.

## Arms

All arms use one prompt template and differ only in what the model is told about the database (`study/run_direct.py`):

| Arm | The model is given |
| --- | --- |
| A, schema | Physical schema of the base tables and the two base views |
| B, base model | A plus the base model: table and column descriptions, keys and joins |
| V, views | A plus the layer's views listed physically, without descriptions |
| S, semantics | B plus the layer: its views, documented columns, keys, joins and glossary |

B − A measures the base model's descriptions; S − B measures the semantics layer; V separates the views themselves from their documentation.

**Arm C, Auto Ontology** (`study/run_auto_ontology.py`): NVIDIA Auto Ontology's own SQL agent at the pinned commit with the documented compatibility patch, on the Auto Ontology repository's questions. The agent, database contents, chat model and requests are fixed; only the imported model differs: C-base imports the base model over a database without layer views, C-semantics imports the extended model over the database with them.

## Models and settings

DeepSeek v4.1 Flash (`deepseek/deepseek-v4.1-flash-1017`) and NVIDIA Nemotron 3.5 Lightning (`nvidia/nemotron-3.5-lightning`), both through OpenRouter, temperature 0, reasoning disabled, at most 4,000 output tokens. After an SQL error the model sees the error and may try again, up to three runs in all.

Arms A, B, V and S: every question, every arm, both models, **five complete repetitions**. Arm C: three complete runs per variant with DeepSeek, three requests at a time, then the same with Nemotron; a Nemotron run that fails for provider reasons is discarded whole and listed.

## Scoring

- **Snapshot**: the returned rows equal the reference rows on the repository's database: named columns, declared types, multiset equality, and order where the question asks for one.
- **Suite**: the response's final SQL returns the reference SQL's rows on the real database **and** on each of eight counterfactual databases per repository (`study/fuzz.py`, seed 0). The counterfactual databases add files, functions, methods and classes (some reusing existing names, some added to existing classes), direct calls and callback references, imports, bases and test links, remove a few calls, toggle docstrings and change some file and definition sizes (new base classes never create an inheritance cycle, which Python forbids), with new edges biased towards what each question names. A query that answers the real database by coincidence fails here. This follows test-suite accuracy (Zhong, Yu and Klein, *Semantic Evaluation for Text-to-SQL with Distilled Test Suites*, EMNLP 2020).
- Every query, the model's or the reference's, is stopped after 60 seconds; a stopped query counts as an error (call graphs have cycles, and a recursive query without a cycle check never ends).
- The denominator is every question. A request that fails for any reason counts as wrong. No question is rerun on its own; a run interrupted by an infrastructure failure is discarded whole, listed with its reason, and repeated.
- Reported per arm, model and repository: snapshot and suite accuracy with the spread over repetitions, paired per-question wins and losses between arms, SQL attempts, latency, tokens and cost as reported by the provider.

## Validity checks run before any model

- `study/suite_power.py` counts, per question, the counterfactual databases on which the reference answer changes; questions whose answer never changes are listed, since suite and snapshot coincide for them.

- Substituting each reference SQL for the model's reply scores every question correct on both measures (`run_direct.py --dry-run-reference`).
- `tests/semantics/` checks every layer view against an independent Python computation on random code maps.

## Frozen state before any model run

- 48 questions (12 per repository); 48 of 48 author–annotator agreements; 17 reworded, none removed (`study/questions/adjudication.md`).
- Reference SQL substituted for the model: 48/48 snapshot, 48/48 suite.
- Reference answer changes on at least one counterfactual database for 44 of 48 questions (`study/results/suite_power.json`); for the other 4, suite equals snapshot.

## What the study does not show

The questions were written by AI annotators under the rules above, not by the repositories' maintainers. Reference answers are correct relative to the extracted database; the extractor's own accuracy is a separate question, recorded per question by the authors' source checks. The counterfactual databases test a query's meaning against the perturbations they contain, not every possible database.

## Amendments

None.

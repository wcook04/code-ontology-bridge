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

**5 November 2026, 10:35 UTC, during the first repetition of arms A, B, V and S.** One run (Nemotron, arm A, httpx, repetition 1) was killed by the operating system when a model-written query exhausted the machine's memory. From this point every DuckDB connection in the runner and scorer has a 1,500 MB memory limit and two threads, so such a query fails with an ordinary error and counts as a wrong answer. The killed run is discarded whole and repeated under the same settings as every later run; it is listed in `study/results/discarded.md`. Runs completed before this point are unaffected by the change except for queries that would have exceeded the limit, which would also have stopped the run.

**5 November 2026, before any run it affects.** Arm C gains a third variant, **C-native**: Auto Ontology's ingestion and agent on the same database (without layer views) with no model imported, so the agent works only from the catalog Auto Ontology builds itself. This compares the bridge's model with Auto Ontology out of the box. It runs `run_live.sh` with the model-import step removed (the exact script is saved in each run's `inputs/`), three runs per model, after the C-base and C-semantics runs (`study/run_c_native.sh`). The summary adds the paired comparisons C-native → C-base and C-native → C-semantics.

## Corrections after the runs

These were made after every run had finished and after the results were published. They change how saved responses are scored, never the responses. The original scores remain published in [`results/frozen/`](results/frozen/).

**5 November 2026, evaluator version "corrected".** An outside review found that the reference SQL of `ao-03` does not restrict the returned symbols or the intermediate to functions and methods, although the question does; `code.symbols` also holds classes, which appear as callers (calls in a class body) and callees (constructor calls). Four auditors, one per repository, then checked all 48 references against their questions' wording without seeing any response or score ([`questions/audit/`](questions/audit/)). The decisions were committed (`9097b80`) before rescoring:

- 21 references that omit a restriction their question states are corrected ([`questions/corrections.json`](questions/corrections.json)); 15 of them involve the same missing function-or-method restriction.
- For 5 questions whose wording supports two readings, either reading is accepted, provided the response follows one reading on all nine databases.
- The counterfactual databases are regenerated with one generator fix: a new file under any `tests/` folder is a test file, the extractor's rule. The original generator marked such files as non-test unless the folder was the top-level `tests/`.
- No corrected reference changes its answer on a real database, so snapshot scores are unchanged; only suite scores move. Rescoring the frozen references on the regenerated databases reproduces the frozen scores exactly, so every change in suite score comes from the corrected references.

**Settings of arm C, stated precisely.** The "Models and settings" paragraph above describes arms A, B, V and S, whose requests set temperature 0, reasoning off and at most 4,000 output tokens. Arm C sends chat through Auto Ontology's own clients, with Auto Ontology's own output limits (8,192 tokens by default) and the provider's default temperature and reasoning settings: these runs used the OpenAI-compatible client, which sends no temperature at the pinned revision, and the patch's reasoning switch applies only to its ChatNVIDIA client. (Corrected 6 November 2026: this paragraph first said temperature 0.) Auto Ontology's responses carry no provider cost or token counts; the study reports them as not captured.

**Wording of the suite measure.** "A query that answers the real database by coincidence fails here" overstates it. Suite agreement means the query returns the reference rows on the real database and on all eight counterfactual databases; it catches many, not all, queries that are right by coincidence, and it approximates semantic accuracy in the sense of Zhong, Yu and Klein.

**Arm C treatment, stated precisely.** C-semantics differs from C-base in two ways: its database contains the six layer views, and the imported model describes them. The agent, its chat model, the source facts and the requests are the same across C-native, C-base and C-semantics.

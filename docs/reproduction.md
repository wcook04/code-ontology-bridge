# Reproduce the example

There are three separate activities: building a code map, testing its compatibility with Auto Ontology, and running Auto Ontology's live question-answering service. Only the last requires model credentials.

## Build the recorded source map

Use Python 3.12 and uv. The repository pins Python 3.12 because its optional PostgreSQL test dependency is excluded on later Python versions.

Run this in a disposable checkout: `reproduce.sh` writes the tracked example exports. It uses the upstream checkout's actual contents and revision; it does not enforce the revision below for you.

```sh
git clone https://github.com/wcook04/code-ontology-bridge.git
git clone https://github.com/NVIDIA/auto-ontology.git auto-ontology-source
git -C auto-ontology-source checkout --detach cdaf61e1bd0cf3820d11d72b43bb460816aebbd3
cd code-ontology-bridge
export AUTO_ONTOLOGY_CLONE="$(cd ../auto-ontology-source && pwd)"
uv sync --locked
sh examples/auto-ontology/reproduce.sh "$AUTO_ONTOLOGY_CLONE"
uv run pytest -q -ra
```

The script creates a map and summary, DuckDB database, model YAML, and evaluation dataset under `examples/auto-ontology/`. It fixes the build timestamp to the source commit time. With the same source and dependencies, text exports are intended to match byte for byte; DuckDB rows should match even when the database file bytes differ.

The recorded fresh run used bridge revision `34285a2ed7440bc07bbe5e17f16452e6c48b50f0`. Its [manifest](../examples/auto-ontology/live/current/manifest.json) binds the exact patch, model, questions, contracts and runner files. Later documentation changes do not change those frozen inputs.

## Check without a model service

```sh
uv run pytest -q -ra
uv run python tools/check_repository.py
```

The tests cover extraction, exports and governance. Some load classes or schemas from the pinned NVIDIA checkout; others need the generated DuckDB file, PostgreSQL support or an older DuckDB runtime. Inspect the skipped-test report rather than treating a green result as proof that every integration ran. No API credentials are needed for these tests.

To check only the local user journey, use the [README example](../README.md#build-the-exports-locally). It needs no NVIDIA checkout.

## Run a fresh 22-question evaluation

Apply the [upstream patch](../examples/auto-ontology/live/upstream-fix/README.md) to a separate Auto Ontology checkout and install its environment with `uv sync --frozen`. Keep the clean source checkout for rebuilding the dataset.

The fresh-run driver requires PostgreSQL 17 with pgvector and `pg_trgm`. Its default PostgreSQL binaries are at Homebrew's `/opt/homebrew/opt/postgresql@17/bin`; set `PG_BIN` for another installation. Store `NVIDIA_API_KEY` and `OPENROUTER_API_KEY` in an environment file outside the repository.

From the bridge root:

```sh
uv run python examples/auto-ontology/live/fresh_run.py \
  "$PWD/build/fresh-evaluation" \
  /absolute/path/to/patched-auto-ontology \
  /absolute/path/to/models.env
```

The output directory must not already exist. The driver snapshots the evaluation, [output contracts](../eval/answer_contracts.json), model YAML and upstream patch before starting. It runs all 22 questions once, with SQL routing enabled and three concurrent requests. The model is `deepseek/deepseek-v4.1-flash-1017` through OpenRouter, with NVIDIA embeddings and reranking. Later model availability and outputs may differ.

The model YAML built by the current reproduction script does not preload the seven example analyses. They remain available in the exported dataset as examples. Requests include the authored question, its existing hint and the explicitly requested column names/types; reference SQL and answers are used only after the response for scoring.

The driver uses isolated local ports 54339 (PostgreSQL), 3111 (backend), 3101 (keyless backend) and 3102 (ingestion). Ensure they are free. The lower-level `run_live.sh` accepts `PG_PORT`, `AO_BACKEND_PORT`, `AO_KEYLESS_PORT` and `AO_INGEST_PORT` overrides, and requires a new absolute `AO_RUN_DIR`. It creates its own cluster, ingests and imports the model, then compiles it before issuing questions. Cleanup stops only that run's services.

The job directory contains `manifest.json`, `status.json`, `score.json`, frozen inputs and the service captures under `run/`. `status.json` records completion or failure. `score.json` separates requested-column completeness, typed value equality, ordering and non-placeholder prose. It does not automatically judge the semantic quality of prose. A failed answer remains part of the run; a new protocol requires a new complete run and directory.

This section reproduces the recorded 22-question walkthrough run (the earlier experiment, before the 48-question [study](../study/RESULTS.md)). The [recorded run](../examples/auto-ontology/live/RESULTS.md) scores 22/22 on strict rows. Its automatic prose check also passes 22/22, but manual review finds question 2's explanation is the single word "Purple". To re-score its saved responses without a model call or modifying retained evidence:

```sh
mkdir -p build/rescore
cp examples/auto-ontology/live/current/responses/10i_ask_with_key/ask_q*.json build/rescore/
uv run python examples/auto-ontology/live/evaluate_run.py \
  build/rescore \
  examples/auto-ontology/live/current/inputs/evaluation.json \
  examples/auto-ontology/live/current/inputs/contracts.json
```

This reproduces the recorded 22/22 strict-row score in [score.json](../examples/auto-ontology/live/current/score.json). The automatic prose check accepts any non-placeholder text, so question 2's "Purple" passes it; [RESULTS.md](../examples/auto-ontology/live/RESULTS.md) records that review. To rescore the 48-question study instead, see [study/RESULTS.md](../study/RESULTS.md#reproduce). The upstream schema-only versus semantic-layer benchmark remains a separate, unrun experiment.


## Validation

The closeout checks on 4 November 2026 passed:

- **80 bridge tests** with the pinned upstream checkout and generated example database available.
- **65 tests in a fresh isolated clone**, with 15 integration tests explicitly skipped because that clone lacked the optional upstream checkout and generated DuckDB file.
- **611 scoped upstream tests**, plus lint, formatting and clean patch application; see the [patch receipt](../examples/auto-ontology/live/upstream-fix/validation.json).
- Wheel installation in a separate environment, then extraction, DuckDB export and model export from outside the source checkout.
- Source/wheel package inspection, working-tree and staged layout checks, local Markdown links, captured-artifact hashes, and credential/private-path scans.
- Visual inspection of all three PDF pages and the published GitHub README at desktop and phone widths.

[Hosted CI passed for the closeout commit](https://github.com/wcook04/code-ontology-bridge/actions/runs/41825926632). It runs the default suite, staged layout check and package build; optional integration coverage is supplied by the local run above. The clone commands use the default `main` branch.

### Illustrated paper revision

The subsequent paper/README revision passed **82 tests** with the same pinned upstream checkout available, plus the working-tree and staged layout/link checks. The local extraction and both export commands in the README were exercised again. The paper builder embeds four shared figures in a six-page PDF and uses public `main` links instead of the deleted development branch. Every PDF page was visually inspected, including the corrected caller/callee arrowheads. These editorial checks do not add model runs or change the retained evaluation score.

### Website backend and review corrections

The inspection-backend revision passed **86 local tests**, including 18 backend
cases; **14 optional upstream tests were skipped** because this invocation did
not supply `AUTO_ONTOLOGY_CLONE`. The saved NVIDIA CSVs and all 22 answers were
loaded by the backend tests, including exact Q11 caller/depth agreement and
separate Q14 prose review. A fresh wheel environment exercised extraction,
bundle generation and a WSGI request outside the source checkout. Source and
wheel builds, the repository layout/link check and all six rendered PDF pages
were checked. These checks do not rerun the model experiment or validate the
patch against newer upstream revisions.

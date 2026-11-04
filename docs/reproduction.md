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

The original bridge revision was `b8ed6f201bc6c2c2e402ba39169b71e0acb99250`. To replay that exact implementation, check it out before installing. The current documentation corrects the interpretation of the saved experiment; it does not replace its captured outputs.

## Check without a model service

```sh
uv run pytest -q -ra
uv run python tools/check_repository.py
```

The tests cover extraction, exports and governance. Some load classes or schemas from the pinned NVIDIA checkout; others need the generated DuckDB file, PostgreSQL support or an older DuckDB runtime. Inspect the skipped-test report rather than treating a green result as proof that every integration ran. No API credentials are needed for these tests.

To check only the local user journey, use the [README example](../README.md#try-it-locally). It needs no NVIDIA checkout.

## Run the live service

The [live results and replay instructions](../examples/auto-ontology/live/RESULTS.md#reproduction) describe the native PostgreSQL 17/pgvector service, environment variables and request sequence. Read the [upstream patch instructions](../examples/auto-ontology/live/upstream-fix/README.md) before starting.

Build the map from a clean pinned source checkout, then run the patched service from a separate checkout. The map describes the original source; the patch enables the public-model configuration used to query it.

The live script recreates its local databases and replaces capture directories. Use a disposable bridge checkout and preserve each new run separately. Keep model credentials outside the repository. Later model availability and stochastic outputs can differ from the recorded experiment.

The historical procedure consists of a three-question trial, an initial 22-question run and five selected reruns with forced SQL routing. A fresh 22-question SQL-only run would be a new experiment. The upstream schema-only versus semantic-layer benchmark remains unrun.

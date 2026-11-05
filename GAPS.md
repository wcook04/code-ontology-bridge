# Capabilities and remaining work

The bridge exports a Python source map, imports it into Auto Ontology and lets its database agent query the resulting rows. The [three-arm comparison](examples/auto-ontology/live/RESULTS.md) measured what the exported semantic model and Auto Ontology each add, with two models on 22 development and 16 held-out questions. This file tracks current limits. Earlier development observations remain in Git history.

## Current evaluation limits

| Issue | Evidence | Remaining work |
| --- | --- | --- |
| Author-written questions, one repository | All 38 questions and reference queries were written by the author, about Auto Ontology's own code. | Questions written by someone else; a second repository. |
| One run per arm | Each arm ran each set once; 16 held-out questions is a small sample. | Repeated runs to estimate run-to-run variation. |
| Ambiguous wording | Held-out [Q101](examples/auto-ontology/live/experiment/deepseek/auto_ontology-heldout/responses/ask_q101.json) says "functions or methods"; Auto Ontology excluded a constructor call the reference counts. | Questions reviewed for a single reading before the next freeze. |
| Prose can be a stub | Development [Q2](examples/auto-ontology/live/current/responses/10i_ask_with_key/ask_q2.json) has correct rows and the explanation "Purple". | Response validation that examines substance; a finite placeholder list is insufficient. |
| Schema-qualification errors | Twelve of 22 first queries in the DeepSeek development run omitted the `code.` schema and needed a repair. | Report upstream; the catalog could give qualified names. |
| No Nemotron held-out result inside Auto Ontology | The runner sent Nemotron through the OpenAI-compatible client, which cannot switch reasoning off; the amended runs through ChatNVIDIA were rate-limited by the NVIDIA API ([discarded runs](examples/auto-ontology/live/experiment/discarded.txt)). | Repeat both Nemotron arm C runs through ChatNVIDIA on a key with a higher rate limit. |
| Upstream benchmark not run | Exports and compatibility tests use NVIDIA's dataset contracts. | Run NVIDIA's own benchmark harness on the exported dataset. |

Every run is retained as collected. No question was asked again, and no reference changed after a run.

## Source-analysis limits

The extractor is static. Imports bind only in the function, method or class that contains them, and calls inside a nested function count for the enclosing function only when it runs that nested function; both were corrected, and the database rebuilt, before the comparison ran. It misses dynamic calls, omits module-level calls from the call table, and records callback references without proving they execute. Only 9,442 of 31,178 direct call sites in the example resolve to an internal symbol. The 349 rows labelled `unresolved` are a residual category, not all unresolved behavior: 11,794 more are dynamic attribute calls. Test links are associations based on imports and filenames, not coverage. Missing descriptions stay empty.

Repeated qualified definitions now receive line-qualified IDs, preserving property getter/setter ownership; ambiguous targets remain unresolved. See the [extractor](code_ontology_bridge/codemap/) and [tests](tests/codemap/). This repair does not make static resolution complete for arbitrary Python programs.

## Data and model integration

The [DuckDB exporter](code_ontology_bridge/export/duckdb_export.py) writes a storage format accepted by the pinned upstream connector. The model supplies table descriptions, terms, attributes and keys; the [dataset tests](tests/export/test_dataset.py) compare reference queries across DuckDB and PostgreSQL. A model import supplies metadata, while an ingested database supplies queryable rows.

The live runner remaps model catalog IDs to existing server IDs before import and waits for compilation after ingestion/import. These fix the demonstrated startup path. Re-import and metadata refresh across changing source snapshots still need separate validation. The upstream DuckDB connector does not itself expose all declared key metadata. Imported term provenance uses the bridge ID namespace and snapshot metadata rather than a dedicated upstream source field.

## Website inspection

The [inspection backend](docs/inspection-api.md) serves source-map rows, bounded call neighborhoods and explicitly selected saved answers. It supplies a portable JSON bundle, a read-only API and a static publication builder. The Q11 descriptor connects selected source spans, extracted rows, frozen model definitions and the recorded question; callback-on/off presets are tested against the saved dataset. The [reading website](site/README.md) is deployed at https://wcook04.github.io/code-ontology-bridge/ as static pages over the static publication; it runs no model and no SQL. The included Python server is for local development; a public live API would need its own WSGI host and HTTPS proxy. It does not run new model queries or establish runtime call coverage. Saved evidence checks bind selected artifact hashes and the source revision. New runs record a canonical typed-table digest from the input database; the historical run has no such binding. Submitted/remapped model YAML, the catalog ID mapping, a full compiled-model export and per-question retrieved context were not retained. The saved post-compilation terms response is exposed only as a partial readback. Source excerpts require an explicitly selected snapshot with matching file hashes. Model and result annotations do not establish retrieval provenance.

## Governance boundaries

The [governance commands](docs/governance.md) are local additions with local tests. Certification records a check and plans updates to existing flags; it does not force the agent to query only certified definitions. A reference-query check proves row agreement, not the truth of descriptive text. Source freshness is checked when a command runs; no watcher keeps server flags synchronized automatically.

Revoking a column-attribute certification now preserves the parent term ID so the planner can clear the server flag when given the live ID map. That repair has a regression test; the fresh question evaluation makes no new live certification claim. SQL annotation infers candidate references after generation, rather than recording retrieval provenance. Definition reconciliation is deterministic but does not judge semantic equivalence.

## Upstream compatibility

The [twelve-file patch](examples/auto-ontology/live/upstream-fix/README.md) covers public-client selection, Nemotron thinking controls, SQL-route forwarding and literal placeholder rejection. Its scoped validation passed 611 upstream tests, lint and format checks. It is a local patch against a pinned revision, not an accepted upstream change.

**G14 remains open:** compilation-success accounting can conceal structured-output failures. A completed scheduler job is not a content-quality check. The patch does not repair that accounting. The tested public routes also do not establish compatibility with NVIDIA's internal gateway or every model provider.

The whole upstream test suite and held-out evaluation remain unrun. Local tests, clean installation and hosted CI are recorded in the [reproduction guide](docs/reproduction.md#validation).

# Capabilities and remaining work

The code map was imported into Auto Ontology, queried through its agent, and used to set certification flags through its existing routes. This tracker separates those observed integrations from local sidecars and remaining work. The original G1 to G15 identifiers are retained so that earlier results still have a destination.

The evidence is for Auto Ontology at the source revision recorded in the [live results](examples/auto-ontology/live/RESULTS.md). “Observed live” below refers to the supplied backend run, not a new run during this review. “Historical report” identifies an observation whose individual response capture was overwritten. References to test sources describe what those tests exercise; current validation is recorded in the repository change history. “Local” identifies a bridge sidecar rather than an enforced upstream policy.

## Data and model integration

The bridge supplies rows and a model document that describe the same source snapshot. Auto Ontology supplies the connectors, catalog, semantic layer and query agent.

| ID | Capability and observed behavior | Bridge contribution | Evidence and remaining boundary |
|---|---|---|---|
| G1 | The existing DuckDB connector accepts the code map. | Eight entity tables and two views in schema `code`; DuckDB export with compatible storage format. | Observed live: 10 catalog objects and 67 columns. The exporter writes storage compatibility `v1.5.0`; the compatibility test opens it with DuckDB 1.5.5. See [exporter](code_ontology_bridge/export/duckdb_export.py), [connector tests](tests/export/test_duckdb.py) and [results](examples/auto-ontology/live/RESULTS.md). |
| G2 | Auto Ontology uses declared keys, but its DuckDB connector reports empty primary- and foreign-key metadata. | Model YAML and PostgreSQL DDL declare eight primary keys and ten foreign keys. | Observed live: ingestion alone had no declared keys; an empty-store import supplied the keys and ten semantic foreign keys. Later compilation removed a relationship involving the empty headings table. See [model export](code_ontology_bridge/export/model_export.py) and [results](examples/auto-ontology/live/RESULTS.md). |
| G8 | The evaluation repository accepts relational dataset folders. | A folder with 22 questions, reference SQL, recorded results and seven saved analyses. | The supplied bridge test mirrors the upstream seed order and compares DuckDB and PostgreSQL query results; that test was not rerun in this review. The upstream benchmark harness has not been run. See [dataset test](tests/export/test_dataset.py) and [evaluation data](examples/auto-ontology/auto_ontology_code/evaluation.json). |
| G9 | Import assigns live UUIDs and retains payload ids as `imported_id`. | An explicit imported-id to live-id map for certification requests. | Historical report and inspected source: the response bodies did not expose `imported_id`. Unmapped targets remain unsent. See [planner](code_ontology_bridge/governance/certification.py) and [results](examples/auto-ontology/live/RESULTS.md). |
| G10 | Import matches identity by payload/live id; a database name is unique. A new `cob:` id can conflict with an already connected catalog. | Import before connecting, or remap catalog ids to the existing live ids before import. | The historical report records a conflicting import failing without changing the store; the successful remapped import has a surviving capture. See [remapping helper](examples/auto-ontology/live/remap_catalog_ids.py) and [results](examples/auto-ontology/live/RESULTS.md). Re-import preserves identity; metadata refresh across later snapshots needs separate verification. |
| G11 | The model-import term schema has no `source` field; imported terms use `source="semantic"`. | Origin in the `cob:<database>:` id namespace and source metadata in the YAML header and snapshot. | Historical report for the eight imported terms, consistent with the inspected importer. The header is explanatory metadata, not an upstream term-source field. See [model export](code_ontology_bridge/export/model_export.py). |

The source facts are ordinary rows. For example, each source file is a row of `code.files`; the ontology term Source file describes that table. Imports and calls are keyed relations. This is why the existing text-to-SQL pipeline can query a codebase.

## Certification, answer annotation and reconciliation

These sidecars add explicit records around Auto Ontology's existing interfaces. They do not change the agent's retrieval or query-validation policy.

| ID | Capability and observed behavior | Bridge contribution | Evidence and remaining boundary |
|---|---|---|---|
| G3 | Auto Ontology's query validators do not enforce certification flags in the reviewed source. | Checks that plan certification-flag updates through existing PATCH routes. | Historical report: three requests returned 200 and set flags; a failed check was withheld. Certified-only retrieval remains unimplemented. See [certification code](code_ontology_bridge/governance/certification.py) and [live results](examples/auto-ontology/live/RESULTS.md). |
| G4 | Auto Ontology stores certification booleans and the row's last edit metadata. | An append-only local event log recording check, actor, source fingerprint, commit and revocation target. | Supplied tests cover the event/state logic; the historical report records live PATCH writes. Freshness is recomputed on command invocation. Stale and failed targets are withheld by default; `--unset-stale` plans false flags. An existing server user is needed for `modified_by`. See [governance guide](docs/governance.md) and the column-attribute revocation issue below. |
| G5 | An MCP `DataAnswer` exposes the answer, SQL, rows, row count, truncation and reasoning. | An offline wrapper associates SQL-derived table/column references with model terms and local certification state, plus a supplied snapshot. | Local tests only. The captures do not demonstrate this wrapper on a live answer. Its `model` field identifies the supplied YAML; it does not identify the language model or prompt. This is an annotation of returned SQL, not a record of the agent's retrieval. See [evidence implementation](code_ontology_bridge/governance/evidence.py). |
| G6 | Auto Ontology qualifies colliding term names to preserve unambiguous table ownership. | A separate pre-import reconciliation policy: canonical id, canonical name, declared resolution, unique alias, then ambiguity or new-term proposals. | Local examples cover competing revenue definitions and repeated module names. Declared resolutions require a reason and decider. Definition text is not evaluated for semantic equivalence, and this command does not automatically modify the exported model. See [worked example](code_ontology_bridge/governance/examples/worked_example.json). |
| G7 | Corrections can be made through existing edits. | Certification events retain a local history and can identify changed checked sources. | No automatic correction-to-recompilation loop has been demonstrated. No automated watcher synchronizes a source change, local status and live server flags. |

### Column-attribute revocation follow-up

Revoking the only effective certification for a column attribute currently leaves its local state as `revoked`, but the status row loses the parent term id. The planner then produces a non-ready column-attribute route even when the caller supplied both live ids. This was reproduced locally during the documentation audit; no live mutation was made. The relevant branches are `status()` and `plan_patches()` in [certification.py](code_ontology_bridge/governance/certification.py). Preserve the parent term id in revoked state before claiming that revocation can clear every supported live flag. The existing tests cover SQL-attribute revocation, not this column-attribute case.

## Public model API compatibility and routing

The [patch review](examples/auto-ontology/live/upstream-fix/README.md) describes the changes and their validation. These findings concern the public endpoints and model configurations used in this experiment. The maintainers' tested Claude configuration on NVIDIA's internal gateway was not available for this run.

| ID | Recorded finding | Contribution and status |
|---|---|---|
| G12 | The default chat model in the supplied `.env.example` returned HTTP 410 in the recorded public-API calls. | The patch changes the default model name. Endpoint availability is a dated observation, not a permanent property of the project. |
| G13 | Structured-output calls with the tested Nemotron configuration timed out and fell back to a request field rejected by the public endpoint. | The patch adds a reasoning switch and configurable client selection. The recorded patched compilation completed without the previous structured-output errors. See the before/after evidence and precise timing scope in [results](examples/auto-ontology/live/RESULTS.md). |
| G14 | A compilation log reported successful completion alongside failed structured-output calls. | The supplied patch does not correct compilation-success accounting. Per-stage failure reporting remains a follow-up. |
| G15 | Some questions about code were routed to the information agent, which answers from catalog metadata. The source facts needed for those questions were table rows. | The patch exposes the agent's existing `calculation_only` option through the chat API. Five selected questions were rerun using it. The two passes and their scoring remain separate in [results](examples/auto-ontology/live/RESULTS.md); this is not a single automatic-routing run. |

## Source-analysis limits

**G16: repeated qualified definitions.** A valid property getter and setter can both become `a.py::A.x`, conflicting with the symbols primary key. The duplicate was independently reproduced during return review. The current analyzer and ID resolver need to distinguish definitions before arbitrary Python repositories can be exported reliably. This does not change the recorded NVIDIA snapshot.

**G17: reconciliation display names.** Definitions with the same canonical ID but different display names take the first name supplied. Assignment precedence is fixed; the resulting display name is not independent of input order. See `reconcile.py`'s construction of the canonical output.


The map is a static Python analysis. Callback rows identify possible invocation paths at low confidence. Dynamic dispatch, references stored in collections, local shadowing and excluded module-level calls limit its completeness and precision. Test links express imports and filename matches rather than measured coverage. Descriptions preserve source-docstring wording with whitespace normalized. The complete snapshot limits are in [summary.json](examples/auto-ontology/summary.json).

The governance log is a local file with caller-supplied actors, without signatures or concurrency locking. It does not observe later edits made in Auto Ontology's UI. A passing check establishes the property that check implements, such as docstring agreement or reference-query reproduction. It does not establish general software correctness. See the [governance guide](docs/governance.md) for operational details.

# Website inspection backend

The backend lets a frontend explain the repository from its existing data: browse
files and symbols, follow calls, inspect the table model, and read the exact
requests and results of the saved NVIDIA experiment. It adds no model service,
new extraction algorithm or website layout.

## Start with the recorded example

From this checkout, after `uv sync --locked`:

```sh
uv run cob inspect-export \
  --dataset examples/auto-ontology/auto_ontology_code \
  --evidence examples/auto-ontology/live/current \
  --out build/inspection/bundle.json
uv run cob inspect-serve --bundle build/inspection/bundle.json
```

The first command uses the committed CSV exports and saved answers. Neither
command requires an NVIDIA checkout, a model key or a database server.
The API listens on loopback at `http://127.0.0.1:8767/api/v1` (`--port` changes
the port). Stop it with Ctrl-C. This is a local development server.

To inspect another source map, use the existing extractor:

```sh
uv run cob build code_ontology_bridge --out build/codemap.json
uv run cob inspect-export --codemap build/codemap.json --out build/inspection/local.json
uv run cob inspect-serve --bundle build/inspection/local.json --port 8768
```

Evidence is opt-in. A bundle without `--evidence` reports `not_supplied` and an
empty question list. It never borrows results from the NVIDIA example. Only
explicitly selected inputs are read; there is no directory discovery at request
time. Review source docstrings and repository metadata before publishing a
bundle from a private repository: those values are intentionally included.

## Contract for a frontend

All data routes return `schema_version: cob_inspection_api_v1`, `revision` and
`data`. The revision is SHA-256 of the canonical bundle payload. It identifies
content, not a signature, freshness check or new experiment. The source commit
and source fingerprint remain separate in `snapshot`.

`GET /api/v1/openapi.json` returns a standard OpenAPI 3.1 document without the
data envelope. Its table schemas come from the same definitions as the exports.

| Route | Data and query parameters |
| --- | --- |
| `/api/v1` | Snapshot, routes, limits and execution boundary. |
| `/api/v1/overview` | Source summary, package counts, known analysis limits, saved run configuration, scores and manual review. |
| `/api/v1/schema` | All eight table definitions, keys, foreign keys, column descriptions and allowed values. |
| `/api/v1/tables/{table}` | Rows from `snapshot`, `files`, `headings`, `symbols`, `class_bases`, `calls`, `imports` or `test_links`. Supports `q`, `limit`, `offset`, and exact filters named after that table's columns. |
| `/api/v1/graph` | Required `symbol_id`; optional `direction=callers\|callees`, `depth`, `call_kind=all\|direct\|callback`, `include_tests=true\|false`, `max_nodes`, `max_edges`. |
| `/api/v1/questions` | Recorded question summaries, automatic scores and separate review findings; `limit`, `offset`. |
| `/api/v1/questions/{id}` | Full submitted question and hint, generated SQL, result tables, explanation, reference SQL/rows, score, review finding and saved artifact hash. |
| `/api/v1/bundle` | Complete portable dataset, including all tables and selected evidence. Prefer paginated routes for interactive use. |

Lists contain `items`, `total`, `limit`, `offset` and `next_offset`. Default page
size is 25, maximum 100. Rows are sorted by the existing primary keys; questions
follow the saved manifest's order. An offset beyond the end returns an empty
page. Keep the same revision while paging; restart pagination if it changes.

`q` is a case-insensitive literal substring of row values, not SQL, a regular
expression or a relevance ranking. It accepts 1–160 nonblank characters. Exact
column filters combine with it using AND. Boolean filters use `true` or `false`;
integer filters are nonnegative decimals. Nullable targets can be inspected in
the returned rows; there is no null-filter syntax in v1.

For example:

```sh
curl 'http://127.0.0.1:8767/api/v1/tables/symbols?name=resolve_semantic_fks'
curl 'http://127.0.0.1:8767/api/v1/tables/files?package=auto_ontology.semantic&is_test=false'
curl 'http://127.0.0.1:8767/api/v1/questions/11'
```

Use the returned `symbol_id` unchanged when requesting its graph. With a frontend
HTTP client, use its query-parameter encoder: symbol IDs contain `/`, `::` and
sometimes `@`. For file details, filter `files` by `file_id`, `symbols` by
`file_id`, `imports` by `file_id`, and `test_links` by `target_file_id`. This keeps
one schema owner instead of introducing separate copies of those relationships.
Source links use a validated GitHub repository URL, full commit and line number;
otherwise `source_url` is null. They do not serve files from the host machine.

## Graph meaning and bounds

Breadth-first traversal assigns each node its shortest depth from the selected
symbol. The root has depth 0. `callers` traverses backwards; `callees` traverses
forwards. Each returned edge retains the original caller, callee, call site,
resolution, confidence and `call_kind`, so arrows always point caller-to-callee.
Cycles terminate through the visited-node set. Distinct call occurrences stay
distinct edges even when they connect the same symbols.

Default depth is 1 (maximum 5), with 100 nodes (maximum 200) and 200 edges
(maximum 500). `truncated` means a node or edge cap omitted an eligible edge.
`depth_limited` means an eligible unseen neighbor existed at the depth boundary.
Neither flag means that the static extractor found every runtime relationship.
If `include_tests=false`, test symbols are excluded from expansion, except for
an explicitly selected root. Paths through excluded test symbols are therefore
also excluded. Limits and filters must remain visible to a frontend user.

Unresolved calls remain inspectable in the calls table but do not create graph
nodes. Callback references retain low confidence; they are not execution traces.
Test links remain associations, not coverage. The overview carries the full
source-analysis limits from the snapshot. For Q11, a depth-5 reverse traversal
outside tests returns the same four caller identities and depths as the saved
answer; the backend computes that traversal locally, without asking a model.

## Evidence and publication

The exporter checks the selected manifest, score, manual review, evaluation
input and each final response against the retained `artifacts.json` hashes.
The source commit must match the experiment's upstream commit. That is a
revision check, not a fresh comparison with the original DuckDB file's bytes.
The manifest's bridge revision describes the experiment, not the current server.
The artifact manifest is local evidence, not an independent attestation.

Only the exact request fields and final answer fields needed for inspection
are projected. Service logs, environment files, intermediate thoughts and
unrelated local files are excluded. The original captures remain unchanged.
Automatic scores and manual review are separate: Q14's table passed while its
single-word explanation failed review. Every evidence response is historical;
the backend cannot start an evaluation or answer a new natural-language question.

The roughly 13 MB example bundle can be hosted as a static JSON asset alongside
a future website. A client can read it directly and implement filtering, or
use the API for bounded server-side responses. Keep generated bundles in ignored
`build/`; regenerate them from their owners rather than maintaining another
committed copy. The complete bundle is capped at 64 MiB.

For a server deployment, embed `code_ontology_bridge.inspection.http.Application`
in a WSGI server, passing the result of `load_bundle(Path(...))`. The included
single-request development listener is not a public hosting stack. Put a public
WSGI server behind a same-origin HTTPS proxy with request/concurrency limits.
Hosting, authentication, cross-origin policy and frontend assets are separate
work; none is deployed by these commands. There is no arbitrary SQL, filesystem
path, model-call, upload, mutation or reload endpoint. Restart with a newly built
bundle to change the snapshot.

Only GET and HEAD are accepted; other methods return 405 with `Allow: GET, HEAD`.
Unknown identities return 404; invalid, duplicate or unknown parameters return
400. Query strings are limited to 4096 characters. Responses support ETag,
If-None-Match and HEAD. No permissive CORS headers are supplied. Treat docstrings,
questions and explanations as untrusted text when rendering them in a future UI.

## Source ownership and verification

`codemap/schema.py` owns table definitions, `codemap/builder.py` owns extraction,
and `export/` owns exported formats. `inspection/bundle.py` projects those formats
and selected saved evidence; `inspection/api.py` owns in-memory queries;
`inspection/contract.py` describes them; `inspection/http.py` adapts them to WSGI.
The CLI only selects inputs and starts those operations. No runtime module
imports repository maintenance tools, private CodeMap services or agent files.

The snapshot, revision, bounded graph and WSGI separation follow the existing
[Plectis component API](https://github.com/wcook04/plectis/blob/main/src/microcosm_core/component_http.py)
pattern. Its implementation and contract were inspected; this backend uses the
bridge's own table model and evidence format rather than importing Plectis.

Run `uv run pytest -q tests/inspection` for the backend checks and
`uv run python tools/check_repository.py` for layout and links. Tests exercise
actual retained data, Q11 parity, evidence tampering, cycles, caps, filters,
pagination, HEAD/ETag, invalid requests and a real HTTP round trip. A successful
read verifies access to the snapshot; it is not a rerun of the NVIDIA experiment.

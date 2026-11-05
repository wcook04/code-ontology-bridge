# Deploy the inspection data

The deployment entry is [data/index.json](https://wcook04.github.io/code-ontology-bridge/data/index.json).
It points to an immutable publication manifest under `data/releases/<sha256>/`.
This is a read-only static data backend on GitHub Pages, not a hosted Python
process. General filtering and graph queries remain available through the
[local inspection API](inspection-api.md). No model execution is exposed.

## Build

From the repository root with the locked environment installed:

```sh
uv run python tools/build_publication.py --fetch-source --out build/publication
```

The output directory must be new. The build uses the committed dataset, frozen
run and Q11 descriptor. It fetches only the four case-selected Python files from
the exact upstream commit and checks every full-file SHA-256 against the dataset.
Use `--source-root /path/to/pinned/source` instead for an offline build. All
published excerpts must be verified; the release does not silently omit them.
It neither runs the NVIDIA service nor rewrites the experiment.

The manifest retains the existing raw JSON resources and adds `api_routes`:
exact logical request keys mapped to saved API response envelopes. Publication
SHA-256 covers the manifest without its own digest field; resource receipts cover
exact bytes, including the final newline. Bundle revision identifies input data;
publication SHA identifies the representation and contract too.

## Stage and publish

Commit and validate source changes before staging a release. Clone the existing
`gh-pages` branch into an ignored build directory (choose a new path):

```sh
git clone --single-branch --branch gh-pages \
  https://github.com/wcook04/code-ontology-bridge.git build/pages
uv run python tools/stage_publication.py \
  --publication build/publication --site build/pages \
  --source-commit "$(git rev-parse HEAD)"
git -C build/pages add .nojekyll data
git -C build/pages diff --cached --stat
git -C build/pages commit -m "Publish inspection data"
git -C build/pages push origin gh-pages
```

`stage_publication.py` verifies manifest and resource hashes before updating the
pointer, refuses to alter an existing immutable release, and preserves frontend
files and earlier releases. GitHub Pages is configured for `gh-pages` at `/`.
Never force-push the deployment branch or replace its root with a data-only
export after a frontend has been added. A concurrent remote update requires a
fresh checkout and re-staging rather than overwriting it.

Before reporting deployment complete, check the Pages build status, fetch the
public entry and immutable manifest, verify resource hashes, open the Q11 source
step and all 22 question records. A successful branch push alone is insufficient.
Run the public verification command once Pages has finished:

```sh
uv run python tools/verify_publication.py --receipt build/live-verification.json
```

It fetches every published JSON resource, checks byte hashes and API revisions,
and follows every outcome and walkthrough-step link. HTTP failures, stale source
commits (when `--expected-source-commit` is supplied), missing routes and changed
resources fail the command. The receipt records the exact deployment checked.

The deployed pointer includes the source commit for traceability. Rollback means
restoring the previous `data/index.json` in a new deployment commit; keep immutable
releases intact for readers already using them.

[Frontend handoff](frontend-handoff.md) includes a small manifest-driven client.
The root website is reserved for that frontend; the data deployment itself adds
no page design.

## Deploy the website

The reading website in [site/](../site/README.md) is built separately and copied beside `data/`:

```sh
(cd site && npm ci && npm test && npm run build)
uv run python tools/stage_site.py --dist site/dist --site build/pages
git -C build/pages add -A .
git -C build/pages commit -m "Deploy the reading website"
git -C build/pages push origin gh-pages
```

`stage_site.py` refuses a build that contains `data/` or a checkout that lacks `data/index.json`, replaces only the earlier website files, and keeps every published release.

## Initial rollout record — 4 November 2026

Source commit `a4021fb544fb401c7183b9e239b36dba0ed3832c` and Pages commit
`1853968e3547a47207c4ecad0ed917936ff9e067` were pushed. The first
[Pages build](https://github.com/wcook04/code-ontology-bridge/actions/runs/41863748701)
queued during GitHub's [Actions and Pages incident](https://www.githubstatus.com/incidents/xr3myzj7ms51),
reported at 16:05 UTC. At this checkpoint, hosting had not yet been verified;
there was no pending deployment approval. Refresh that build's status and run
the verification command before describing the initial rollout as live. The
queued deployment can proceed automatically when GitHub's runners recover.

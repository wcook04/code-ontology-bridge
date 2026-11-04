# Claude frontend handoff

Build an engaging, visual, click-through explanation of **code-ontology-bridge**.
Give someone a clear way from actual Python source to the answer Auto Ontology
returned, with Q11 as a useful starting example and all 22 outcomes available
for inspection. The backend is ready; the frontend's form is deliberately open.

Choose the visual language, layout, navigation, interaction model and stack that
best explain the material. The six backend steps are evidence addresses, not a
required six-screen wizard. Explore the earlier sites for ideas that fit; there
is no requirement to copy their appearance, combine their components, or refactor
them. Build in this repository, keeping its existing interfaces and frozen run.

## Start here

- [Deployment data entry](https://wcook04.github.io/code-ontology-bridge/data/index.json)
- [API contract and local server](inspection-api.md)
- [Deployment and reproducible build](deployment.md)
- [Q11 narrative](../README.md#one-question-all-the-way-through)
- [All results and scoring explanation](../examples/auto-ontology/live/RESULTS.md)
- [Paper](case-study.md) and [existing figures](figures/README.md)

Check the [initial rollout record](deployment.md#initial-rollout-record--4-november-2026) and current public entry before assuming hosting is ready. The queued Pages deployment was affected by a GitHub service incident; local builds remain usable.

The hosted data is a static publication of real Python API responses. It needs
no model keys or service credentials. Fetch `data/index.json`, follow its relative
`manifest`, then resolve `manifest.api_routes[route]` relative to that manifest.
Pin that manifest for the session. Never construct a resource filename or fetch
the 14 MB bundle just to open Q11. Its assembled walkthrough is about 56 KB;
the complete outcome list is about 14 KB, before transport compression.

```js
const entryURL = 'https://wcook04.github.io/code-ontology-bridge/data/index.json';
async function readJSON(url) {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`Data request failed: ${response.status}`);
  return response.json();
}
const entry = await readJSON(entryURL);
const manifestURL = new URL(entry.manifest, entryURL);
const manifest = await readJSON(manifestURL);
async function readRoute(route) {
  const asset = manifest.api_routes[route];
  if (!asset) throw new Error(`Route is unavailable in this publication: ${route}`);
  const response = await readJSON(new URL(asset, manifestURL));
  if (response.revision !== manifest.revision) throw new Error('Mixed data revisions');
  return response.data;
}
const walkthrough = await readRoute(manifest.delivery.entry_route);
const outcomes = await readRoute(manifest.delivery.outcomes_route);
// On selecting an outcome:
const question = await readRoute(outcomes.items[0].question_route);
```

Static hosting supports exactly the keys in `api_routes`; appending query
parameters to a JSON filename does not filter it. The complete 22-item list can
be filtered in the browser. Arbitrary graph traversals and table queries require
the local Python API or an explicit future server deployment. The walkthrough
already carries both useful Q11 graph presets. See the manifest's `delivery`.

## What the backend gives you

`/api/v1/walkthroughs/caller-chain-q11` contains linked source, records, model,
request, SQL and answer steps. Each has a stable ID and its own route. It includes:

- Commit-pinned source links and file-hash-verified excerpts, including the
  scheduler's callback occurrence at line 203.
- Exact extracted records and two graphs: all relationships and direct calls
  only. Including the callback adds the scheduler; it does not prove execution.
- Selected native entity terms, their represented tables and columns, plus
  explicit availability of the historical model stages.
- The complete submitted request, output contract, generated SQL, reference SQL,
  original result rows, answer, score, review and deterministic source links.

`/api/v1/outcomes?limit=100` contains all 22 questions, links to their complete
records, and independent table/prose statuses. Q2 fails strict row matching and
has unknown prose classification; Q14 matches the rows but fails prose review.
The complete run has 21 table matches and 20 substantive prose assessments.
These are development questions and author review, not an independent benchmark.
The `population_*` fields always describe the full run, even on a filtered local
API response. Question detail preserves nulls, types, ordering and multiplicity.

A function is a source row; “Code symbol” is an entity term describing a table.
The exported model is captured. The full compiled model, remapped import payload
and retrieved context are not. The partial compiled terms response is only that.
Do not animate an invented retrieval or execution trace to bridge those gaps.
Source excerpts, model descriptions, SQL and answers must render as text, not
untrusted HTML. Backend notes and status fields carry the factual boundaries;
they need not become a wall of implementation details in the reading experience.

## Earlier work to explore

These are references, not a visual specification. Look at the live interaction
and its actual implementation before deciding whether it helps this project.
Use or adapt a useful implementation where appropriate, retaining its license
and notices if code is copied; you have broad freedom over the final result.

| Reference | Useful questions to explore | Actual source inspected for this handoff |
| --- | --- | --- |
| [Proof Reader](https://wcook04.github.io/proof-reader/#/contextual-embeddings) | How can source inspection preserve reading position and make Back feel reliable? | [ReadingPane](https://github.com/wcook04/proof-reader/blob/e2df8880a892cc13ece046709f649c1860487b00/web/src/paper/ReadingPane.tsx), [history](https://github.com/wcook04/proof-reader/blob/e2df8880a892cc13ece046709f649c1860487b00/web/src/app/history.ts), [router](https://github.com/wcook04/proof-reader/blob/e2df8880a892cc13ece046709f649c1860487b00/web/src/app/router.ts). Local checkout: `/Users/willcook/src/proof-reader`. |
| [Zenith](https://wcook04.github.io/plectis-zenith/) | How can a reader move between a readable result and its exact recorded payload? | [JsonView](https://github.com/wcook04/plectis-zenith/blob/c09e6e9c4f8ac16eb649dc7724afdb8daa7367d8/site/src/components/JsonView.tsx), with neighboring Inspector and Results components. Local checkout: `/Users/willcook/src/plectis-zenith`. |
| [SK / Lean exposition](https://wcook04.github.io/lean-exposition-site/) | How can an explanation, relationship and supporting record remain connected while exploring? | [RecordPanel](https://github.com/wcook04/lean-exposition/blob/f5a1403cda5ddc4152dff76d56bb3058c4f9367b/site/src/panels/RecordPanel.tsx), [static export](https://github.com/wcook04/lean-exposition/blob/f5a1403cda5ddc4152dff76d56bb3058c4f9367b/site/scripts/export-static.py). Local checkout: `/Users/willcook/src/lean-exposition`. The backend adapts its route-to-static-response pattern. |
| [Plectis Atlas](https://wcook04.github.io/plectis-atlas/) | How can preview, selection and return-to-reading work across mouse, keyboard and phone? | [inspect.js](https://github.com/wcook04/plectis-atlas/blob/276627f55e02d29b57b4bee563147e32a23f776d/site/assets/inspect.js). Local checkout: `/Users/willcook/src/plectis-atlas`. |

Those sites solve different subject-matter problems. Their mathematical badges,
trust labels and paper content do not transfer automatically to static code
analysis. No requirement to reuse all four, or to stop discovery at this list.

## Check the experience you choose

A reader should be able to follow Q11 to actual source, see why the callback
changes the result, inspect the exact request and SQL, and open any of the 22
outcomes without losing their place. Make Q2 and Q14 straightforward to inspect.
Keep direct links and browser Back useful. Check keyboard access, narrow screens,
loading/error states and reduced motion in the actual rendered site.

Run the repository's tests and layout gate after changes. New frontend files need
an explicit owner in `tools/check_repository.py`, package/build commands and a
small README map update. Deploy frontend assets without removing `data/`; the
backend staging tool already preserves other site files. Leave a working site,
verified links and a short account of what you built and tested.

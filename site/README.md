# Reading website

The website at https://wcook04.github.io/code-ontology-bridge/ explains what this project does and lets a reader follow one recorded question, question 11, from a line of Python in Auto Ontology's scheduler to the rows Auto Ontology returned. It also lists all 22 recorded questions, each with its request, SQL, returned rows, reference rows and the two separate assessments.

The site reads only the static publication described in [deployment](../docs/deployment.md): it fetches `data/index.json`, follows the pinned manifest and resolves each API route through `manifest.api_routes`. It runs no model and no SQL. Missing, failed and empty data are shown as three different states, and nothing is substituted when a request fails.

## Build and run

Use Node 20.19 or later.

```sh
cd site
npm ci
npm test
npm run dev      # http://localhost:5181, serving ../build/pages-release/data as ./data
npm run build    # writes site/dist, which contains no data
```

Set `COB_DATA_DIR` to serve a different staged `data/` directory during development. To deploy, stage the publication first, then copy the built site beside it; `tools/stage_site.py` replaces the earlier site files and keeps `data/`:

```sh
uv run python tools/stage_site.py --dist site/dist --site build/pages-release
```

## Where things are

| Path | What it holds |
| --- | --- |
| `src/data/` | The publication client (manifest pinning, revision checks) and response types. |
| `src/views/` | The front page with its five-step example, the outcome list, one question, one source excerpt. |
| `src/components/SystemDiagram.tsx` | The drawn split between this project and Auto Ontology, adapted from `docs/figures/architecture.png`. |
| `src/components/CallerGraph.tsx` | The caller graph from the two published presets. Positions never move between presets. |
| `src/components/Term.tsx`, `src/app/glossary.ts` | Glossary words: plain names in prose, with exact identifiers in a card. Adapted from the Plectis site's term previews. |
| `src/styles/family.css` | Shared header and footer parts, copied unchanged from Will Cook's other sites. |

## Rules the pages keep

- A recorded answer, SQL statement or score never changes when the graph view changes.
- Long identifiers stay out of prose; they appear in glossary cards, record views and result tables, breaking only at `/` and `::`.
- Captured text renders as text, never as HTML. SQL shown with added line breaks can always be shown exactly as captured.

The public web audit (`tools/meta/frontend/public_web_audit.py` in the author's workspace) reports the site's `#/` routes as broken in-page anchors; they are hash routes, not anchors. The one straight quote it reports is inside a recorded SQL condition and stays as recorded.

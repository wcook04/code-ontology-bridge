# Reading website

The website at https://wcook04.github.io/code-ontology-bridge/ explains what this project does and has two kinds of page:

- **The study** (`#/study`): the 48-question study's scores, directly and inside Auto Ontology, and a per-question grid whose rows open the full question and a link to every run's saved answer. It fetches `study/summary.json`, a copy of `study/results/summary.json` staged beside the site; that file is not part of the pinned `data/` publication.
- **The walkthrough** (the front page and `#/walkthrough/...`): one recorded question, question 11, followed from a line of Python in Auto Ontology's scheduler to the rows Auto Ontology returned, and the 22 recorded walkthrough questions with request, SQL, returned rows, reference rows and both assessments. These pages read only the static publication described in [deployment](../docs/deployment.md): they fetch `data/index.json`, follow the pinned manifest and resolve each API route through `manifest.api_routes`.

The site runs no model and no SQL. Missing, failed and empty data are shown as three different states, and nothing is substituted when a request fails.

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
| `src/views/` | The front page with its five-step example, the study and its question grid (`StudyGrid.tsx`), the outcome list, one question, one source excerpt. |
| `src/components/ScoreCard.tsx` | The first screen's comparison: the 12 Auto Ontology questions inside Auto Ontology and asked directly, one tile per question, all computed from `study/summary.json`. |
| `src/components/Films.tsx`, `public/films/` | The short and full videos as linked stills. The stills are local files; the page requests nothing from YouTube. |
| `src/components/SystemDiagram.tsx` | The drawn split between this project and Auto Ontology, adapted from `docs/figures/architecture.png`. |
| `src/components/CallerGraph.tsx` | The caller graph from the two published presets. Positions never move between presets. |
| `src/components/Term.tsx`, `src/app/glossary.ts` | Glossary words: plain names in prose, with exact identifiers in a card. Adapted from the Plectis site's term previews. |
| `src/styles/family.css` | Shared header and footer parts, copied unchanged from Will Cook's other sites. |
| `src/styles/refine.css`, `src/styles/study-grid.css` | The first screen, film thumbnails, the example's opening, the phone header and the study grid. Loaded after `app.css`; they use only the tokens in `tokens.css`. |

## Rules the pages keep

- A recorded answer, SQL statement or score never changes when the graph view changes.
- Long identifiers stay out of prose; they appear in glossary cards, record views and result tables, breaking only at `/` and `::`.
- Captured text renders as text, never as HTML. SQL shown with added line breaks can always be shown exactly as captured.

The public web audit (`tools/meta/frontend/public_web_audit.py` in the author's workspace) reports the site's `#/` routes as broken in-page anchors; they are hash routes, not anchors. The one straight quote it reports is inside a recorded SQL condition and stays as recorded. On a phone the header takes two rows (the name and scheme switch, then the five destinations), which the audit reports as a tall header; the front page's headline and the study's question are checked at 1440 by 900.

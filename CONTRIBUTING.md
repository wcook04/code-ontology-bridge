# Contributing

Use Python 3.12 and install the locked environment with `uv sync --locked`.

```sh
uv run pytest -q -ra
uv run python tools/check_repository.py
```

The layout check validates Git-tracked and nonignored candidate files, documentation links and required reader routes. `--index` checks staged contents for use before a commit. CI runs the local suite and layout check; optional tests still need the pinned upstream checkout and generated database described in [reproduction](docs/reproduction.md).

## Where changes belong

- Runtime behavior belongs in `code_ontology_bridge/`, with tests in `tests/`.
- Authored questions and reference SQL belong in `eval/`. The example dataset is their generated projection.
- Guides belong in `docs/`; keep the root README focused on understanding and trying the project. Shared paper/README figures and their source briefs belong in `docs/figures/`.
- Repository maintenance commands belong in `tools/`.
- Live replay tools, compatibility patches and the current run evidence remain together under `examples/auto-ontology/live/`.

Do not rewrite a saved response, score or log to make a new interpretation agree with it. Explain revised judgments in `RESULTS.md` and preserve the original scoring. Earlier captures may leave the current tree after their replacements are retained and links repaired; their original commits remain the historical record. New experiments need separate capture directories and their own source, configuration and scoring details. Never commit model credentials or local environment files.

`docs/case-study.md` is the paper source. Run `sh tools/build_paper.sh` with Pandoc and Tectonic installed to refresh `docs/case-study.pdf`, then inspect its pages. The build uses Pandoc's article template and adapts the typography and margins of the returned paper draft. It embeds local figures and points document links at `main`; it can run from any working directory.

The [figure briefs](docs/figures/README.md) record source references, relationships and omissions. When editing a generated illustration, check every label and arrow against those sources. Review it at the PDF's 166 mm text width and in the GitHub README; a successful build does not establish that a diagram is correct or readable. Keep preview pages in ignored `build/`, and reuse the same accepted assets in the paper and README.

Known behavior gaps belong in [GAPS.md](GAPS.md), with an implementation pointer and reproducible evidence. Keep source-analysis limitations separate from failures in the upstream service or the experiment's scoring.

The [inspection backend](docs/inspection-api.md) lives in `code_ontology_bridge/inspection/`, with tests in `tests/inspection/`. Its bundles are generated outputs under ignored `build/`, not a new evidence authority. Keep its table definitions derived from `codemap/schema.py`; preserve exact saved requests and separate automatic scores from manual review. Changes to its API must update the contract, guide and HTTP tests together. No HTTP route may execute supplied SQL, start model jobs or select a host path.

Publication cases belong beside the example's replay tools, outside frozen
`live/current/`. Their captions are editorial; source/model/question references
are validated by `inspection/publication.py`. Keep generated publication assets
in ignored `build/`. Do not replace a missing historical model payload with a
new export or interpret missing review findings as success. A partial terms
readback is not a full compiled model. Tests must validate real JSON responses
against OpenAPI and exercise cycle edges at the depth boundary, parallel call
occurrences, caps and traversal through excluded test symbols.

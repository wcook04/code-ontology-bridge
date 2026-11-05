# Documentation

Choose a starting point by what you want to check or do.

| Task | Start here |
| --- | --- |
| Understand the contribution | [Paper](case-study.md) or [PDF](case-study.pdf): source-to-SQL integration, the callback example, results and limits. |
| Check the evaluation | [Study results](../study/RESULTS.md): 48 questions, four repositories, every response, both evaluator versions; [protocol](../study/PROTOCOL.md). |
| Inspect the walkthrough answers | [Earlier experiment](../examples/auto-ontology/live/RESULTS.md): the 22-question walkthrough run and the 38-question comparison, with scoring rules and review. |
| Run the software | [Quickstart](../README.md#quickstart), then [pinned reproduction](reproduction.md) for the live Auto Ontology run. |
| Build a website against the data | [Inspection API](inspection-api.md): Q11 source-to-answer resources, frozen semantic model, all 22 outcomes, static publication command and API contract. |
| Deploy the data | [Deployment guide](deployment.md): verified source build, immutable releases and GitHub Pages publication. |
| Review the adapter | [Interface specification](../SPEC.md) and [compatibility patch](../examples/auto-ontology/live/upstream-fix/README.md). |
| Understand the additional commands | [Governance](governance.md): certification history, SQL-derived annotations and reconciliation. |
| Change a figure, the paper or the website | [Figure sources and briefs](figures/README.md), [contributing](../CONTRIBUTING.md) and the [frontend notes](frontend-handoff.md). |
| Find known limits | [Capabilities and remaining work](../GAPS.md). |

`case-study.md` is the maintained paper source. `sh tools/build_paper.sh` generates its PDF using the images in `figures/`. The README reuses those same images. Keep image briefs and attribution beside the assets; keep generated page previews in ignored `build/`.

The recorded JSON, SQL, CSV and logs stay under `examples/auto-ontology/`. Editorial changes do not rewrite those observations. Authored evaluation inputs live under `eval/`; copies inside the retained run describe what that run used.

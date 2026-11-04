# Documentation

Choose a starting point by what you want to check or do.

| Task | Start here |
| --- | --- |
| Understand the contribution | [Paper](case-study.md) or [PDF](case-study.pdf): source-to-SQL integration, the callback example, results and limits. |
| Inspect what the model returned | [Detailed results](../examples/auto-ontology/live/RESULTS.md): all 22 answers, scoring rules and review. |
| Run the software | [Local example](../README.md#build-the-exports-locally), then [pinned reproduction](reproduction.md) for the NVIDIA experiment. |
| Build a website against the data | [Inspection API](inspection-api.md): Q11 source-to-answer resources, frozen semantic model, all 22 outcomes, static publication command and API contract. |
| Review the adapter | [Interface specification](../SPEC.md) and [compatibility patch](../examples/auto-ontology/live/upstream-fix/README.md). |
| Understand the additional commands | [Governance](governance.md): certification history, SQL-derived annotations and reconciliation. |
| Change a figure or the paper | [Figure sources and briefs](figures/README.md) and [contributing](../CONTRIBUTING.md). |
| Find known limits | [Capabilities and remaining work](../GAPS.md). |

`case-study.md` is the maintained paper source. `sh tools/build_paper.sh` generates its PDF using the images in `figures/`. The README reuses those same images. Keep image briefs and attribution beside the assets; keep generated page previews in ignored `build/`.

The recorded JSON, SQL, CSV and logs stay under `examples/auto-ontology/`. Editorial changes do not rewrite those observations. Authored evaluation inputs live under `eval/`; copies inside the retained run describe what that run used.

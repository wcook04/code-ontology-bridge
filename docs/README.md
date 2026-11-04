# Documentation

Start with the [repository overview](../README.md) for what the bridge does and a local example.

- [Case study](case-study.md) ([PDF](case-study.pdf)): the two starting systems, the adapter, the experiment and what its results establish.
- [Reproduction](reproduction.md): build the pinned dataset, check compatibility and locate the live-run instructions.
- [Governance](governance.md): certification history, SQL-derived answer annotations and definition reconciliation.
- [Detailed results](../examples/auto-ontology/live/RESULTS.md): all 22 answers from the fresh complete run, scoring rules and saved evidence.
- [Capabilities and remaining work](../GAPS.md): what is implemented, what was observed and known defects.
- [Interface specification](../SPEC.md): table definitions and export contracts.

The case study's Markdown is the maintained source. `sh tools/build_paper.sh` generates its PDF. The experiment's recorded JSON, SQL, CSV and logs remain under `examples/auto-ontology/`; editorial corrections do not rewrite those observations.

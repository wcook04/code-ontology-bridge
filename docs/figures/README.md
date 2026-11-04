# Paper figures

These four illustrations explain different parts of the [paper](../case-study.md). The root README reuses the architecture and caller-chain images. The images were generated and edited with OpenAI image generation on 4 November 2026; they are explanatory drawings, not captured model output or application screenshots.

These notes define what each image must show. To revise an image, supply the current PNG as a reference, preserve the listed relationships, and check the result against the linked source. Generation is not deterministic. Never accept an arrow or a label solely because it appeared in a generated image.

## Sources and attribution

The architecture adapts the separation of agent/backend, semantic catalog and source database in [NVIDIA's architecture image](https://github.com/NVIDIA/auto-ontology/blob/cdaf61e1bd0cf3820d11d72b43bb460816aebbd3/docs/assets/arch.png). It replaces the general deployment diagram with the bridge's two exports and query path. NVIDIA logos, icons and branding are not reused. The other figures adapt the resulting publication style and use this repository's schema and recorded evidence.

The upstream reference is part of NVIDIA Auto Ontology, under [Apache License 2.0](https://github.com/NVIDIA/auto-ontology/blob/cdaf61e1bd0cf3820d11d72b43bb460816aebbd3/LICENSE). Its README carries: Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved. The adapted illustrations are distributed under this repository's [Apache License 2.0](../../LICENSE).

## Architecture

[architecture.png](architecture.png) answers: **How can Auto Ontology query source code without a new code-specific connector?**

Use a white background, thin outlines, regular-weight single-line labels and a visible enclosure for upstream components. Keep titles and explanations in the surrounding document, not in the image. Show Python source entering the bridge, then splitting into model YAML and DuckDB rows. YAML goes through import and compilation to the semantic catalog. The catalog supplies context to the database agent. A question enters the agent; SQL leaves it for the DuckDB connector. The connector also reads the exported data and produces the query result. The enclosure, rather than color alone, identifies upstream ownership.

Sources: [model exporter](../../code_ontology_bridge/export/model_export.py), [DuckDB exporter](../../code_ontology_bridge/export/duckdb_export.py), [upstream connector](https://github.com/NVIDIA/auto-ontology/blob/cdaf61e1bd0cf3820d11d72b43bb460816aebbd3/auto_ontology/connectors/duckdb.py) and [import schema](https://github.com/NVIDIA/auto-ontology/blob/cdaf61e1bd0cf3820d11d72b43bb460816aebbd3/auto_ontology/server/model_interchange/schemas.py).

The figure omits ingestion services, catalog ID mapping, model providers, retries and answer narration. The output label is “Query result”; the connector executes SQL rather than generating it. The short labels Extractor, Catalog, SQL agent and Connector correspond to the bridge, semantic catalog, database agent and DuckDB connector. Both teal export boxes remain outside the upstream enclosure. There is no arrow claiming YAML creates data. Use a single forward query path; avoid ambiguous return connectors.

## Source tables

[source-tables.png](source-tables.png) answers: **How does a call become something SQL can follow?**

Show selected fields from `code.files`, `code.symbols` and `code.calls`. Preserve exactly three directed foreign-key connections:

- `symbols.file_id` to `files.file_id`.
- `calls.caller_symbol_id` to `symbols.symbol_id`.
- `calls.callee_symbol_id` to `symbols.symbol_id`.

Both call connections enter the `symbol_id` cell at visibly separate heights. Give that cell extra space; keep arrowheads away from horizontal dividers and text. The `file_id` connection must start and end in the two `file_id` rows. Keep this spacing when revising the figure.

Source: [relational model](../../SPEC.md#relational-model-schema-code-postgres-dialect-that-duckdb-also-accepts). Only three of eight tables and selected columns are shown. The caption limits the connection to resolved callees; an unknown callee has no symbol to point to. `description` and `summary` contain source docstrings; the model YAML describes the tables and joins. Missing docstrings remain empty.

## Caller chain

[caller-chain.png](caller-chain.png) answers: **Why does the scheduler appear in the returned caller list?**

Show exactly five symbols, with short role labels: Scheduler, CLI entry, Wrapper, Compiler and FK resolver. The paper table and expandable README reference map each label to its exact source identifier. Never split an identifier at underscores to fit a box. Avoid giant headings, gradients, heavy blocks and pill badges; use thin outlines and unboxed depth labels. Solid arrows run from `main` to `run_semantic_compilation`, from that wrapper to `_run_semantic_compilation`, and from there to `resolve_semantic_fks`. A dashed arrow runs from `SemanticScheduler._run_once` to the wrapper and is labeled “callback”; the caption names `asyncio.to_thread`. The shortest depths to the target are 3 for `main` and the scheduler, 2 for the wrapper and 1 for its body. Arrows point to callees; SQL traverses them in reverse.

Sources: [Q11 response](../../examples/auto-ontology/live/current/responses/10i_ask_with_key/ask_q11.json), [scheduler source](https://github.com/NVIDIA/auto-ontology/blob/cdaf61e1bd0cf3820d11d72b43bb460816aebbd3/auto_ontology/ingestion_service/semantic_scheduler.py), [compilation wrapper](https://github.com/NVIDIA/auto-ontology/blob/cdaf61e1bd0cf3820d11d72b43bb460816aebbd3/auto_ontology/semantic/compile.py) and [CLI caller](https://github.com/NVIDIA/auto-ontology/blob/cdaf61e1bd0cf3820d11d72b43bb460816aebbd3/auto_ontology/semantic/__main__.py).

The diagram omits literal symbol names, full paths and unrelated calls. The source lookup supplies exact names as unbroken text. Put long identifiers in the source table rather than squeezing them into diagram nodes. It shows a static map, not execution or a complete runtime impact analysis. The text and saved response carry the full identifiers and the question's hint.

## Evaluation

[evaluation.png](evaluation.png) answers: **Why are there two reported success counts?**

Show a short main path: 22 responses, Table check, 21 matches, Prose review, 20 pass both. Reference rows feed only the table check. A branch from Table check identifies Q2: extra row; a branch from Prose review identifies Q14: prose stub. The latter response says “thought”. Keep every node label on one line and put the development-set qualification in the caption.

Sources: [results](../../examples/auto-ontology/live/RESULTS.md), [automatic score](../../examples/auto-ontology/live/current/score.json) and [manual review](../../examples/auto-ontology/live/current/review.json). All requests specify output fields; only 18 have hints. The flow groups the reported counts; review covered every answer, not only the 21 matching tables. Internal retries are omitted, so the figure must not call this one-shot accuracy. There is no held-out comparison.

## Review and build

Keep the full meaning in captions and adjacent Markdown as well as in the pixels. The wording pass should remove vague or inflated claims while preserving code identifiers, counts and uncertainty. Read titles, labels and captions in order: source facts become rows; those rows enter an existing database workflow; the callback example exercises it; the evaluation measures its observed outputs.

Run `sh tools/build_paper.sh`, render the PDF with Poppler and inspect every page. Check each image at the paper's 166 mm text width, then inspect the README at desktop and narrow widths. Confirm that the revised source-table arrows enter the intended cells, the caller diagram has exactly four edges, and the evaluation never supplies reference answers to the agent. Keep previews in ignored `build/`.

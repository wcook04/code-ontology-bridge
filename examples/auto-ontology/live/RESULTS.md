# Fresh evaluation: 4 November 2026

**21/22 matching result tables; 20/22 with both matching tables and substantive prose.** The written response is the agent's explanation of its query, which Auto Ontology writes together with the SQL before the query runs; the rows are returned beside it, so the prose describes the calculation rather than the values. This is one complete run of all 22 questions under protocol `explicit-output-v3`. No answer was replaced by a selected rerun.

**How the SQL was reached.** In 15 of the 22 requests the first SQL Auto Ontology ran gave the recorded rows. In six (Q3, Q5, Q11, Q18, Q21, Q22) the first query named a table without its `code.` schema, failed with a DuckDB catalog error, and was fixed by Auto Ontology's rewrite step; Q2 was rewritten twice after its own checks and ran twice. 29 queries ran in all.

**What the instructions asked for.** The shared output instructions ([answer_contracts.json](../../../eval/answer_contracts.json)) ask the agent, after executing SQL, to describe the returned rows. At `cdaf61e` the explanation is written before execution, so no response could follow that part; the rows are returned beside it.

**Known reference defects.** Q11's reference query stops at depth 6 (`depth < 6`); every caller here is within depth 3, so the score is unaffected, but it is not a correct reference for deeper call chains. Q20 groups by the first two path parts, so a script directly under `dev_tools/` counts as its own area; the agent's SQL and the reference both do this. Both references stay unchanged for this run and should be fixed before a new evaluation.

The [original automatic score](current/score.json) reports 21 passes. [Review of every response](current/review.json) reduces the combined count to 20 because Q14's prose is just “thought”. The original score and responses remain unchanged.

## What was run

| Item | Recorded setting |
| --- | --- |
| Source being queried | NVIDIA Auto Ontology `cdaf61e1bd0cf3820d11d72b43bb460816aebbd3` |
| Bridge implementation | `34285a2ed7440bc07bbe5e17f16452e6c48b50f0` |
| Chat model | `deepseek/deepseek-v4.1-flash-1017` through OpenRouter |
| Embeddings / reranking | `nvidia/nemotron-3-embed-1b` / `nvidia/llama-nemotron-rerank-vl-1b-v2` |
| Routing | `calculation_only: true` on every request |
| Collection | One API request per question, three concurrent workers; upstream internal SQL/structured-output retries remain enabled |
| Context | 18 original hints, explicit output fields/types, general identity and caller guidance |
| Saved example analyses imported | None |
| Start / finish | 11:27:10 / 11:50:35 UTC, 4 November 2026 |

The [manifest](current/manifest.json) records model settings and hashes of all frozen inputs and runner files. The [status](current/status.json) confirms normal completion with no changed runner inputs. The model queried eight tables and two views describing 473 files, 168 test files and 5,319 symbols.

## Scoring and review

The strict scorer checks named columns and their types, full case-sensitive identifiers, row multiplicity, and order where the contract requests it. Integer values are exact; numeric transport has an absolute tolerance of 1e-6. A result must complete successfully. The automatic prose check rejects empty text, known placeholders and generic unrelated refusals; it cannot establish semantic correctness.

All 22 final SQL statements, tables and explanations were reviewed. Twenty explanations describe the query or its assumptions; most leave the actual values to the accompanying table. This count is not a measure of polished narrative answers. Matching one result table also does not establish SQL equivalence on other data: some generated queries add filters that happen not to change this snapshot's rows.

### Two remaining problems

**Q2, package description:** the final query uses `module LIKE '%semantic%'` together with `module = package`. That includes both `auto_ontology.semantic` and `auto_ontology.server.semantic_compilation`, yielding the requested description plus an extra empty description. The reference selects exactly `auto_ontology.semantic`. The response does not acknowledge this overbroad match.

**Q14, resolution statistics:** all seven rows, counts and percentages match, but the entire prose response is “thought”. The existing validator rejects several literal stubs, including `test`, `TODO` and `PLACEHOLDER`; this different stub escaped it. The manual review records the failure without altering the response or re-running the question.

## Every answer

Each link contains the exact request, streamed events, final SQL and prose, and returned rows. The `gold_sql` field is appended by the capture script after the response; it is not part of the request.

| Question | Subject | Table match | Prose review |
| --- | --- | --- | --- |
| [Q1](current/responses/10i_ask_with_key/ask_q1.json) | Callers of upsert_table_term | Yes | Query explained |
| [Q2](current/responses/10i_ask_with_key/ask_q2.json) | Semantic package description | No: extra row | Overbroad scope |
| [Q3](current/responses/10i_ask_with_key/ask_q3.json) | Files without descriptions | Yes | Query explained |
| [Q4](current/responses/10i_ask_with_key/ask_q4.json) | Definition and docstring | Yes | Query explained |
| [Q5](current/responses/10i_ask_with_key/ask_q5.json) | Repository counts | Yes | Query explained |
| [Q6](current/responses/10i_ask_with_key/ask_q6.json) | Snapshot identity | Yes | Query explained |
| [Q7](current/responses/10i_ask_with_key/ask_q7.json) | Public functions without test links | Yes | Query explained |
| [Q8](current/responses/10i_ask_with_key/ask_q8.json) | Most-called functions/methods | Yes | Query explained |
| [Q9](current/responses/10i_ask_with_key/ask_q9.json) | Imports of dal/terms.py | Yes | Query explained |
| [Q10](current/responses/10i_ask_with_key/ask_q10.json) | Test associations | Yes | Query explained |
| [Q11](current/responses/10i_ask_with_key/ask_q11.json) | Recursive caller chain | Yes | Query explained |
| [Q12](current/responses/10i_ask_with_key/ask_q12.json) | Package line counts | Yes | Query explained |
| [Q13](current/responses/10i_ask_with_key/ask_q13.json) | Classes with most methods | Yes | Query explained |
| [Q14](current/responses/10i_ask_with_key/ask_q14.json) | Call-resolution statistics | Yes | Stub |
| [Q15](current/responses/10i_ask_with_key/ask_q15.json) | Connector imports | Yes | Query explained |
| [Q16](current/responses/10i_ask_with_key/ask_q16.json) | Modules without importers | Yes | Query explained |
| [Q17](current/responses/10i_ask_with_key/ask_q17.json) | Compilation callees | Yes | Query explained |
| [Q18](current/responses/10i_ask_with_key/ask_q18.json) | Undocumented public symbols | Yes | Query explained |
| [Q19](current/responses/10i_ask_with_key/ask_q19.json) | Mutual package calls | Yes | Query explained |
| [Q20](current/responses/10i_ask_with_key/ask_q20.json) | Transitive import impact | Yes | Query explained |
| [Q21](current/responses/10i_ask_with_key/ask_q21.json) | Test with most source links | Yes | Query explained |
| [Q22](current/responses/10i_ask_with_key/ask_q22.json) | Subclassed but unconstructed classes | Yes | Query explained |

## What the result supports

Auto Ontology's existing database agent can query source-derived rows through the bridge. Q11 follows a callback as well as ordinary call edges; Q19 finds mutually calling packages; Q22 finds a base class with ten non-test subclasses. These are properties of the static map, not proof of runtime impact or test coverage.

The questions were authored during development. Earlier full runs informed the explicit output contracts, distinct-identity guidance, caller wording and placeholder checks. Q11 was clarified to include methods and class-scope callers; all 22 reference SQL statements and answer rows are unchanged from the preceding protocols. The final result is therefore a development-set demonstration, without held-out questions, another repository, a schema-only control or a comparison against direct source reading.

The seven SQL examples distributed in the exported dataset were excluded from the imported model. Audit reconstructed every request from its frozen question, existing hint and public contract, and verified no reference SQL or answer payload was sent. The runner's own internal retries can repair SQL, but the bridge does not supply reference answers to them.

## Evidence and reproduction

- [Frozen inputs](current/inputs/): questions and references, output contracts, model YAML and exact upstream patch.
- [Responses](current/responses/): setup, import, compilation and all 22 question captures.
- [Service logs](current/logs/): logs from this same isolated run, with local paths replaced by placeholders by the runner.
- [Artifact hashes](current/artifacts.json): hashes of retained evidence, including the separate review.
- [Reproduction guide](../../../docs/reproduction.md): data build, local tests and a new complete live run.
- [Upstream patch and validation](upstream-fix/README.md): configuration, routing and structured-output changes.

The current tree contains one full evaluation. Earlier observations remain in Git: the original demonstration at `b8ed6f2`, the first explicit-output full run at `0c57ea1`, and the second at `34285a2`. Removing their capture folders from the current tree does not change those records. The current score uses only the fresh run above.

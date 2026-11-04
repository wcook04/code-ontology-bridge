# Auto Ontology answering questions about its own code

Auto Ontology returned 13 reference-matching tables after normalization or identity checks, eight partial reference tables, and one empty result on the 22-question code-map example. This combines an initial pass over all 22 questions with five targeted reruns after changing their routing. Eleven equivalences come from the scorer; two require the explicit identity comparisons below.

The questions ran through Auto Ontology's chat API with the [public API patch](upstream-fix/README.md), DeepSeek V4.1 Flash for chat, and NVIDIA embeddings and reranking. The bridge supplied the source-code tables, their semantic descriptions, seven SQL examples, and the benchmark's question-specific evidence. The result demonstrates the integration on this curated example. It does not measure performance on unseen repositories or compare against a schema-only baseline.

[Results and scoring](#results-and-scoring) · [One recorded answer](#one-recorded-answer) · [Integration findings](#integration-findings) · [Model experiments](#model-experiments) · [Reproduction](#reproduction)

## Results and scoring

The preserved result files distinguish a successful request from a complete answer. The [reference dataset](../auto_ontology_code/evaluation.json) supplies the questions, optional evidence, SQL, and expected rows. [`score_answers.py`](score_answers.py) compares the returned SQL rows with those reference rows.

| Pass | Scorer-equivalent | Missing reference fields | Unmatched by scorer |
|---|---:|---:|---:|
| [22 questions, default routing](evidence/deepseek_22q_default_routing/10i_ask_with_key/score.json) | 10 | 7 | 5 |
| [Five targeted reruns, `calculation_only`](evidence/deepseek_5q_calculation_only/10i_ask_with_key/score.json) | 1 | 1 | 3 |
| Combined, replacing those five original answers | 11 | 8 | 3 |
| Combined, after the Q15 and Q17 identity checks | 13 | 8 | 1 |

The five original unmatched answers were Q2, Q4, Q10, Q15, and Q17. Auto Ontology classified them as information questions and sent them to its catalog-metadata agent. They concern the contents of the code tables, so the rerun set `calculation_only: true` in each request. The patch exposes that existing agent option through the chat API. A complete 22-question pass under the forced routing policy has not been recorded.

The scorer's exact comparison preserves values, column order, and row order. Its equivalence comparison ignores column names and order, ignores row order, compares strings case-insensitively, reduces a symbol ID to its qualified name, and rounds numbers to one decimal place. The partial comparison requires the same row count and the corresponding ordered items, while allowing reference values to be omitted. Equivalence takes precedence over the partial predicate. These rules compare the saved outputs; they do not establish general SQL equivalence.

### Every selected answer

Links marked “rerun” select the second pass. All other links select the default-routing pass.

| Question | Selected result | Finding |
|---|---|---|
| [Q1: callers of `upsert_table_term`](evidence/deepseek_22q_default_routing/10i_ask_with_key/ask_q1.json) | Equivalent | Five caller identities. |
| [Q2: semantic package purpose, rerun](evidence/deepseek_5q_calculation_only/10i_ask_with_key/ask_q2.json) | Missing field | Correct description; omits its source label. |
| [Q3: undocumented files](evidence/deepseek_22q_default_routing/10i_ask_with_key/ask_q3.json) | Equivalent | All 32 file paths. |
| [Q4: definition and docstring, rerun](evidence/deepseek_5q_calculation_only/10i_ask_with_key/ask_q4.json) | Incorrect | Reads the empty headings table instead of the function summary. |
| [Q5: repository counts](evidence/deepseek_22q_default_routing/10i_ask_with_key/ask_q5.json) | Equivalent | 473 Python files, 168 test files, 5,319 symbols. |
| [Q6: snapshot identity](evidence/deepseek_22q_default_routing/10i_ask_with_key/ask_q6.json) | Missing field | Correct repository and commit; omits the fingerprint. |
| [Q7: public symbols without test links](evidence/deepseek_22q_default_routing/10i_ask_with_key/ask_q7.json) | Equivalent | All five symbol identities. |
| [Q8: most-called symbols](evidence/deepseek_22q_default_routing/10i_ask_with_key/ask_q8.json) | Missing field | Correct ordered ten symbols; omits call counts. |
| [Q9: importers of `dal/terms.py`](evidence/deepseek_22q_default_routing/10i_ask_with_key/ask_q9.json) | Equivalent | All 17 file paths. |
| [Q10: semantic-FK test links, rerun](evidence/deepseek_5q_calculation_only/10i_ask_with_key/ask_q10.json) | Equivalent | Both test files and link reasons. |
| [Q11: static blast radius](evidence/deepseek_22q_default_routing/10i_ask_with_key/ask_q11.json) | Equivalent | Four callers and shortest depths. |
| [Q12: largest packages](evidence/deepseek_22q_default_routing/10i_ask_with_key/ask_q12.json) | Missing field | Correct ordered five packages; omits line counts. |
| [Q13: classes with most methods](evidence/deepseek_22q_default_routing/10i_ask_with_key/ask_q13.json) | Missing field | Correct ordered five classes; omits method counts. |
| [Q14: call-resolution shares](evidence/deepseek_22q_default_routing/10i_ask_with_key/ask_q14.json) | Missing field | Correct labels and rounded percentages; omits counts. |
| [Q15: connector imports, rerun](evidence/deepseek_5q_calculation_only/10i_ask_with_key/ask_q15.json) | Equivalent after identity check | The same 12 modules, written as dotted names. |
| [Q16: modules without importers](evidence/deepseek_22q_default_routing/10i_ask_with_key/ask_q16.json) | Equivalent | All nine reference modules. |
| [Q17: compilation callees, rerun](evidence/deepseek_5q_calculation_only/10i_ask_with_key/ask_q17.json) | Equivalent after identity check | The same seven functions, with files and line ranges. |
| [Q18: packages with undocumented symbols](evidence/deepseek_22q_default_routing/10i_ask_with_key/ask_q18.json) | Missing fields | Correct ordered five packages; omits totals and percentages. |
| [Q19: mutual package calls](evidence/deepseek_22q_default_routing/10i_ask_with_key/ask_q19.json) | Equivalent | All 14 package pairs. |
| [Q20: transitive import impact](evidence/deepseek_22q_default_routing/10i_ask_with_key/ask_q20.json) | Equivalent | All nine package/count rows. |
| [Q21: test file with most source links](evidence/deepseek_22q_default_routing/10i_ask_with_key/ask_q21.json) | Missing field | Correct test-file path; omits the count of 15. |
| [Q22: connector base classes](evidence/deepseek_22q_default_routing/10i_ask_with_key/ask_q22.json) | Equivalent | `SQLDatabase` and 10 non-test subclasses. |

For Q15, replace dots in each returned module name with slashes and append `.py`; the resulting set equals the 12 reference paths. For Q17, join each returned file path and function name with `::`; the resulting set equals the seven reference symbol IDs. Its additional line ranges match the source definitions. These two checks extend the scorer's result; the saved `score.json` files continue to show them as unmatched.

These scores concern returned SQL rows, not systematically rated prose. Q16 matches the reference rows but has a placeholder in its prose-response field.

The eight partial answers are incomplete relative to the reference rows. Some omitted fields go beyond what the question explicitly asks: Q2 requests a description, and Q6 requests a repository and commit. Keeping the omissions visible makes the scoring convention inspectable without changing it after seeing the answers.

## One recorded answer

Q11 asks which functions call `resolve_semantic_fks` directly or indirectly, outside tests, with the shortest depth. Its [saved answer and SQL](evidence/deepseek_22q_default_routing/10i_ask_with_key/ask_q11.json) return:

| Caller | Shortest depth |
|---|---:|
| `_run_semantic_compilation` | 1 |
| `run_semantic_compilation` | 2 |
| `SemanticScheduler._run_once` | 3 |
| `main` | 3 |

The scheduler reaches `run_semantic_compilation` by passing it to `asyncio.to_thread`. The bridge records that function reference as a callback edge, so a recursive SQL query can reach it alongside direct callers. This is the impact set represented by the static graph; dynamic dispatch and calls missing from that graph remain outside its scope.

The request includes prose explaining reverse traversal and callback edges. The imported [SQL examples](../../../eval/custom_analyses.json) also include a blast-radius query targeting this function. In this run, the [backend log](evidence/deepseek_22q_default_routing/backend_keyed.log) reports zero custom analyses retrieved for Q11 and zero in its SQL-construction context. The result should therefore be read as a query over a curated model with supplied task guidance. No held-out generalization test was performed.

## Integration findings

The live service used Auto Ontology's own ingestion service, FastAPI backend, model import, semantic compiler and chat API. The code-map DuckDB database held the source rows; PostgreSQL held Auto Ontology's catalog and semantic layer.

| Area | Observed result | Evidence retained |
|---|---|---|
| DuckDB file format | The earlier file format was refused by upstream's pinned DuckDB. A v1.5.0-storage copy was readable. New bridge exports write that storage version. | [Refusal log](evidence/duckdb_2.0_file_refused_by_their_duckdb_1.5.5.log), [copy check](responses/05a_compat_duckdb_copy.json), [exporter](../../../code_ontology_bridge/export/duckdb_export.py) |
| Connected source and model import | The live catalog IDs were remapped before importing terms, attributes, semantic joins and analyses into the connected source. | [Remapping summary](responses/10b_remap_summary.json), [successful keyed import](responses/10c_model_import_embed_true.json), [remapping helper](remap_catalog_ids.py) |
| Keys | The connector reports no primary or foreign keys. Import supplies declared joins; the live catalog keeps no primary keys on tables skipped as already present. | [Stored counts](responses/10g_postgres_after_compile.txt), [run script](run_live.sh) |
| Semantic compilation | The compiler removed the imported `headings.file_id` semantic FK because this repository's headings table is empty. | [Preserved compilation log](evidence/after_fix_thinking_off/ingestion_keyed.log) |
| Internal chat route | Questions were submitted directly to the FastAPI route used by MCP `ask_question`. | [Request driver](ask_questions.py), preserved answer JSON files |

An earlier keyless run also recorded model import into an empty store, read routes behind the MCP allow-list, stored but unreturned `imported_id` fields, and three certification PATCHes with one intentionally failed check withheld. It found a duplicate-database-name failure when importing onto an ingested catalog without remapping, and different authorization behavior with and without an internal user header. The current tree retains the [run script](run_live.sh), [certification targets](cert_targets.json), and [SQL probes](sql/), but the individual step 1 to 9 response files were overwritten by later runs. These findings need a fresh capture for a complete standalone audit. The [capability tracker](../../../GAPS.md) distinguishes the integration paths and remaining limits.

## Model experiments

The same-model timing comparison concerns Nemotron 3.5 Lightning. The final answer-quality result also changes the model and endpoint.

| Configuration | Compilation and question result | Record |
|---|---|---|
| Original public default model | The original run report records `410 Gone`; its raw logs were overwritten. | Historical observation; patch changes the default name |
| Nemotron 3.5 Lightning, before thinking control | First compilation pass: 663.3 s; 24 log lines report rejected `guided_json`. Q1 was stopped before completion after about 45 minutes. | [Compilation log](evidence/before_fix/ingestion_keyed.log), [backend log](evidence/before_fix/backend_keyed.log) |
| Nemotron 3.5 Lightning, thinking disabled | First compilation pass: 32.1 s, with no `guided_json` rejection in that compilation log. Five question requests completed; none matched the reference rows. | [Compilation log](evidence/after_fix_thinking_off/ingestion_keyed.log), [five answers](evidence/after_fix_thinking_off/10i_ask_with_key/) |
| Nemotron 3.5 Lightning, thinking enabled again | Q1 took 856 s; timeouts returned. | [Answer](evidence/after_fix_thinking_on_partial/10i_ask_with_key/ask_q1.json) |
| DeepSeek V4.1 Flash trial | Three of three answers equivalent under the scorer. | [Trial scores](evidence/deepseek_trial_3q/10i_ask_with_key/score.json) |
| DeepSeek V4.1 Flash full pass and targeted reruns | Combined 13 equivalent after identity checks, eight incomplete, one incorrect. | Result tables above |

The earlier Nemotron Q5 illustrates why successful SQL execution is insufficient. A cross join multiplied the file and symbol counts and returned 2,515,887 symbols instead of 5,319. The later DeepSeek answer used independent counts and matched the reference.

The reported OpenRouter usage was approximately **$0.54 across the trial, the full pass and the targeted rerun**, including their associated model calls. This is an account-usage difference recorded during the session; the counter alone cannot exclude concurrent unrelated usage. It excludes NVIDIA API and local compute costs; a separate billing receipt is not included here.

Auto Ontology's benchmark documentation describes a tested Claude configuration on NVIDIA's internal gateway. That configuration and the full `auto-ontology-eval` harness were not run here. The [patch note](upstream-fix/README.md) describes the public-route changes and the recorded test coverage.

## Reproduction

Rebuild the source map from the clean upstream revision before applying the patch to a separate service checkout. The [repository instructions](../../../docs/reproduction.md) cover installing the bridge and generating its artifacts. Reproducing the 473-file snapshot requires the full upstream checkout, including its tests and development tools.

The following examples run from a **disposable bridge checkout** after its Python environment and example artifacts have been built. `run_live.sh` replaces `responses/`, `logs/`, `cert/`, and `.work/`, and recreates its local databases. It uses native PostgreSQL 17 with `pg_trgm` and pgvector; the recorded machine was macOS. Set `PG_BIN` for your installation.

```sh
export AUTO_ONTOLOGY_CLONE=/absolute/path/to/patched-auto-ontology
export PG_BIN=/opt/homebrew/opt/postgresql@17/bin
sh examples/auto-ontology/live/run_live.sh
```

For the recorded DeepSeek configuration, the external env file must supply `NVIDIA_API_KEY` and `OPENROUTER_API_KEY`. The script reads them into the service processes. Keep that file outside the repository.

```sh
export AO_CHAT_ENDPOINT=https://openrouter.ai/api/v1
export AO_CHAT_KEY_VAR=OPENROUTER_API_KEY
export AO_CHAT_MODEL=deepseek/deepseek-v4.1-flash-1017
export AO_QIDS="1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20 21 22"
unset AO_CALCULATION_ONLY
KEYED_ONLY=1 sh examples/auto-ontology/live/run_live.sh --with-key /absolute/path/to/models.env
uv run python examples/auto-ontology/live/score_answers.py \
  examples/auto-ontology/live/responses/10i_ask_with_key \
  examples/auto-ontology/auto_ontology_code/evaluation.json
```

Preserve that pass before starting another. From the bridge root, this creates a new directory and fails if the name already exists:

```sh
mkdir examples/auto-ontology/live/evidence/replay_default_routing
cp -R examples/auto-ontology/live/responses \
  examples/auto-ontology/live/evidence/replay_default_routing/responses
cp -R examples/auto-ontology/live/logs \
  examples/auto-ontology/live/evidence/replay_default_routing/logs
```

Then run the five targeted questions:

```sh
export AO_QIDS="2 4 10 15 17"
export AO_CALCULATION_ONLY=1
KEYED_ONLY=1 sh examples/auto-ontology/live/run_live.sh --with-key /absolute/path/to/models.env
uv run python examples/auto-ontology/live/score_answers.py \
  examples/auto-ontology/live/responses/10i_ask_with_key \
  examples/auto-ontology/auto_ontology_code/evaluation.json
mkdir examples/auto-ontology/live/evidence/replay_calculation_only
cp -R examples/auto-ontology/live/responses \
  examples/auto-ontology/live/evidence/replay_calculation_only/responses
cp -R examples/auto-ontology/live/logs \
  examples/auto-ontology/live/evidence/replay_calculation_only/logs
```

Set `AO_CHAT_MODEL` explicitly for every keyed run. The retained driver still has the original retired model as its own fallback, independently of the patched upstream defaults. Model availability and stochastic outputs may differ on a later run. Keep the new records separate from the preserved observations linked above.

To repeat the three-question DeepSeek trial, use the same model settings with `AO_QIDS="1 5 11"` and unset `AO_CALCULATION_ONLY`. To inspect the patched Nemotron configuration, unset `AO_CHAT_ENDPOINT`, `AO_CHAT_KEY_VAR` and `AO_CALCULATION_ONLY`, set `AO_QIDS="1 5 11 15 22"`, set `AO_CHAT_MODEL=nvidia/nemotron-3.5-lightning-30b-a3b`, and set both `REASONING_ENABLE_THINKING` and `NON_REASONING_ENABLE_THINKING` to `false`. The reasoning-enabled comparison sets both to `true`; its preserved record contains only the partial run described above. Preserve each configuration's captures separately. The unpatched observations came from the clean Auto Ontology checkout; their saved logs remain the evidence for those historical endpoints and timings.

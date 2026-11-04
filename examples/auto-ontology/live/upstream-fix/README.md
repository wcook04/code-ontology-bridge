# Public model APIs and code-question routing

This patch enabled the recorded Auto Ontology run through public model APIs. It adds explicit chat-client selection, a Nemotron thinking control, and access to the agent's existing SQL-only routing option. On the curated code-map example, the full question pass and five targeted reruns produced 13 reference-equivalent answers after two identity comparisons, eight answers missing reference fields, and one incorrect answer. [Results and request records](../RESULTS.md) explain that combined score.

The bridge's DuckDB data and imported semantic model use Auto Ontology's existing interfaces. This patch changes the model-client and chat configuration used for the recorded question-answering run. No code-specific connector, query planner or SQL engine is added.

The current patch also extends the existing SQL-generation placeholder validator to reject literal stubs such as `test`, `TODO` and `PLACEHOLDER`. Validation failures use the existing bounded structured-output retry mechanism; no reference answer is supplied to that retry. This addition follows review of the fresh code-question runs.

## Changes for review

[`public-api-nemotron.patch`](public-api-nemotron.patch) contains twelve file diffs, including tests and the generated backend OpenAPI schema.

| Change | Behavior | Scope |
|---|---|---|
| Public model default | Replaces the original Nemotron name with the Nemotron 3.5 Lightning name used in the recorded run. | `.env.example` and public-key defaults in `utils/model_config.py` |
| Nemotron thinking control | Sends `chat_template_kwargs.enable_thinking` through ChatNVIDIA for `nvidia/nemotron*` models. The two normal client factories default it to false; each role can enable it explicitly. | `utils/llm_invoke.py` |
| Explicit client selection | Lets each chat role select `ChatOpenAI` or `ChatNVIDIA`, with a shared fallback setting. This permits models with other name prefixes to use an OpenAI-compatible endpoint. | `utils/llm_invoke.py`, using the existing `resolve()` configuration precedence |
| Claude through an OpenAI-compatible route | Preserves LangChain's forced tool choice for `anthropic/` model names. The existing `tool_choice=None` gateway workaround remains for other Claude naming routes. | `_structured_output_kwargs()` |
| SQL-only routing at the chat boundary | Adds `calculation_only: false` to `ChatRequest` and forwards it through the router and worker. True selects the agent's existing calculation-only behavior. | Chat schema, router, worker, worker test and backend OpenAPI |

The motivation for routing is specific to data about code. A question such as “Which functions does this function call?” describes rows in the code-map database, but can resemble a request about catalog metadata. Five benchmark questions took the metadata branch in the default pass. Their rerun requests explicitly set `calculation_only: true`.

## Observed effect

The retained before-and-after compilation logs compare Nemotron 3.5 Lightning on NVIDIA's public endpoint:

| Configuration | First compilation pass | Question observation |
|---|---:|---|
| [Before thinking control](../evidence/before_fix/) | 663.3 s; 24 log lines reporting rejected `guided_json` | Q1 was stopped before completion after about 45 minutes. |
| [Thinking disabled](../evidence/after_fix_thinking_off/) | 32.1 s; no `guided_json` rejection in the compilation log | Five requests completed; their answers did not match the reference rows. |

The logs are consistent with long reasoning exceeding the client's timeout and falling back to a request format rejected by the hosted API. The patch controls reasoning on that route. Some question-answering retries remain in the patched backend log, so the observed improvement is more specific than eliminating every structured-output failure.

The stronger answer result uses `deepseek/deepseek-v4.1-flash-1017` through OpenRouter for the two chat roles, with NVIDIA embeddings and reranking. It changes the model and endpoint as well as applying the patch, and uses targeted routing changes for five questions. It is an integration result, without a controlled estimate of the patch's effect on accuracy.

The original default model's `410 Gone` response is a historical observation from 3 November 2026; its raw logs were overwritten. The replacement model name should be checked against the intended deployment when adopting the patch. The maintainers' tested Claude route on NVIDIA's internal gateway was not available for this run.

## Configuration

These controls are read when clients are constructed. Restart the service processes after changing their environment.

| Setting | Values and default |
|---|---|
| `REASONING_CLIENT` | `openai` or `nvidia`; falls back to `DEFAULT_MODELS_CLIENT`, then existing model-prefix selection |
| `NON_REASONING_CLIENT` | Same precedence for the non-reasoning role |
| `DEFAULT_MODELS_CLIENT` | Optional shared client choice |
| `REASONING_ENABLE_THINKING` | `1`, `true`, `yes`, or `on` enables thinking; unset defaults to false |
| `NON_REASONING_ENABLE_THINKING` | Same behavior for the non-reasoning role |

The thinking request field is added only to the ChatNVIDIA branch for Nemotron-prefixed model names. Selecting `openai` does not send that ChatNVIDIA-specific field. Unrecognized client strings fall back to the existing prefix logic.

For a compatible chat request, the new field is:

```json
{
  "question": "Which functions call upsert_table_term?",
  "calculation_only": true
}
```

The default remains false. The patch does not change the MCP tool's public input schema; the recorded rerun used the FastAPI chat route directly.

## Apply and validate

The patch targets upstream commit `cdaf61e1bd0cf3820d11d72b43bb460816aebbd3`. Use a separate checkout so the clean source snapshot used to build the code map remains available.

From the root of a bridge checkout, after cloning Auto Ontology into a sibling directory and checking out that revision:

```sh
export COB_CHECKOUT="$(pwd)"
git -C ../auto-ontology-source worktree add --detach ../auto-ontology-api \
  cdaf61e1bd0cf3820d11d72b43bb460816aebbd3
git -C ../auto-ontology-api apply --check \
  "$COB_CHECKOUT/examples/auto-ontology/live/upstream-fix/public-api-nemotron.patch"
git -C ../auto-ontology-api apply \
  "$COB_CHECKOUT/examples/auto-ontology/live/upstream-fix/public-api-nemotron.patch"
```

Run the following from the patched Auto Ontology checkout:

```sh
uv sync --frozen
uv run ruff check auto_ontology/server/chat auto_ontology/utils
uv run ruff format --check auto_ontology/
uv run pytest -q -ra auto_ontology/server/chat auto_ontology/utils
COB_OPENAPI_BEFORE="$(mktemp)"
cp docs/openapi/backend.json "$COB_OPENAPI_BEFORE"
uv run python -m dev_tools.generate_backend_openapi
cmp "$COB_OPENAPI_BEFORE" docs/openapi/backend.json
rm "$COB_OPENAPI_BEFORE"
```

The recorded development run passed the scoped Ruff check, reported 433 files already formatted, and passed **178 tests with two warnings** in the chat and utility test trees. Backend OpenAPI was regenerated. These are the recorded checks for those scopes; the entire upstream suite and live internal-gateway compatibility were not exercised. The source subset supplied for documentation review omits the original upstream tests and OpenAPI file, so the 178-test result was not independently repeated in that review.

The patch adds tests for thinking-field construction, environment parsing, the ChatNVIDIA request configuration, and worker forwarding. Dedicated tests for explicit client selection and the `anthropic/` structured-output branch would make those additional behaviors easier to review.

For a live reproduction, use the [run instructions](../RESULTS.md#reproduction). Rebuild the example data from the clean base revision first, and run services from the patched checkout. Set `AO_CHAT_MODEL` explicitly: the bridge's retained run script has its own original-model fallback.

## Remaining boundaries

Compiler success accounting, tracked as [G14](../../../../GAPS.md), is unchanged. The before-fix run logged overall compilation success while also recording structured-output failures; absence of an exception at the scheduler boundary is not a content-quality check. The patch also leaves model-import reconciliation, primary-key ingestion, and certification policy unchanged.

The 22 questions and their context were authored with the bridge. Seven imported SQL examples overlap some tasks, and the benchmark supplies question-specific evidence. The [result note](../RESULTS.md#one-recorded-answer) identifies the Q11 overlap and the saved retrieval observations. Additional repositories, held-out questions and a fixed routing policy would be the next checks for broader performance claims.

# Public model APIs and SQL routing

This local patch lets the pinned Auto Ontology service use configurable public model clients and exposes its existing SQL-only route through the chat API. The [fresh complete run](../RESULTS.md) used DeepSeek v4.1 Flash through OpenRouter with NVIDIA embeddings and reranking: 21/22 matching tables, 20/22 with substantive prose. This is an integration observation, without a controlled estimate of the patch's effect on accuracy.

The [patch](public-api-nemotron.patch) contains twelve file diffs, including tests and generated OpenAPI. It adds no code-specific connector or query engine.

| Change | Purpose |
| --- | --- |
| Explicit OpenAI/NVIDIA client selection per role | Use public OpenAI-compatible endpoints without relying only on model-name prefixes. |
| Nemotron thinking control and updated example default | Control reasoning on the tested ChatNVIDIA route; the fresh run sets its DeepSeek model explicitly. |
| Structured tool choice for `anthropic/` names | Preserve LangChain tool choice on that OpenAI-compatible route; the internal-gateway path was not tested. |
| `calculation_only` chat field and worker forwarding | Select the existing SQL pipeline for questions whose answers are code-map rows. |
| Existing placeholder validator extended | Reject literal `test`, `TODO`, `PLACEHOLDER`, `TBD` and `N/A` through existing bounded validation retries. |

The placeholder check is incomplete: the fresh Q14 response was “thought”. Its rows pass, but manual review rejects its prose. No reference SQL or answers are supplied to the retry mechanism.

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

The default remains false. The patch does not change the MCP tool's public input schema; the recorded run used the FastAPI chat route directly.

## Apply and validate

The patch targets upstream commit `cdaf61e1bd0cf3820d11d72b43bb460816aebbd3`. Keep a clean source checkout for rebuilding the map and a separate patched checkout for services.

From the bridge root, after cloning Auto Ontology into the sibling `auto-ontology-source` directory:

```sh
export COB_CHECKOUT="$(pwd)"
git -C ../auto-ontology-source worktree add --detach ../auto-ontology-api \
  cdaf61e1bd0cf3820d11d72b43bb460816aebbd3
git -C ../auto-ontology-api apply --check \
  "$COB_CHECKOUT/examples/auto-ontology/live/upstream-fix/public-api-nemotron.patch"
git -C ../auto-ontology-api apply \
  "$COB_CHECKOUT/examples/auto-ontology/live/upstream-fix/public-api-nemotron.patch"
```

From the patched Auto Ontology checkout:

```sh
uv sync --frozen
uv run ruff check auto_ontology/
uv run ruff format --check auto_ontology/
uv run pytest -q auto_ontology/retrieval/text_to_sql/tests auto_ontology/server/chat auto_ontology/utils
```

The [validation receipt](validation.json) binds the patch hash to 611 passing tests, two warnings, passing lint and 433 already-formatted files. A clean pinned checkout accepted `git apply --check`. These cover the query-pipeline, chat and utility scopes; they are not the entire upstream test suite. The warnings concern deprecated `max_tokens` use and NVIDIA model-type discovery.

For a live run, follow the [reproduction guide](../../../../docs/reproduction.md). The isolated driver freezes inputs, imports no saved analyses, uses the same routing for all 22 requests and retains every response. Set the chat model explicitly when using the lower-level runner.

## Remaining boundaries

Compiler-success accounting ([G14](../../../../GAPS.md#upstream-compatibility)), model-import reconciliation and certification policy are outside this patch. Passing tests and one successful live setup do not establish provider-independent behavior. No NVIDIA outreach or upstream acceptance is implied.

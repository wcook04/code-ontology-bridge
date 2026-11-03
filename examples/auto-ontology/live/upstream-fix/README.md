# Patch for NVIDIA Auto Ontology: public API models and code questions

With this patch, Auto Ontology's own agent runs through public model APIs and answers 21 of 22 questions about Auto Ontology's source code with the right content; unpatched, through NVIDIA's public API, it answered none.

`public-api-nemotron.patch` applies to [NVIDIA/auto-ontology](https://github.com/NVIDIA/auto-ontology) at `cdaf61e` (`git apply public-api-nemotron.patch`). It changes 9 files. With it applied, `ruff check`, `ruff format --check` and `pytest auto_ontology/utils auto_ontology/server/chat` pass (178 tests), and `dev_tools.generate_backend_openapi` has been rerun.

It does four things.

1. **Current default model.** `.env.example` and `auto_ontology/utils/model_config.py` named `nvidia/nemotron-3-nano-30b-a3b`, which `integrate.api.nvidia.com` no longer serves (`410 Gone`). The default becomes `nvidia/nemotron-3.5-lightning-30b-a3b`.

2. **Nemotron reasoning switch.** Nemotron 3.5 reasons before it answers. On long prompts under `response_format` the reasoning outlasts `LLM_INVOKE_TIMEOUT_S` (120 s); ChatNVIDIA then falls back to `guided_json`, which the hosted API rejects (`unknown field guided_json`). `_build_client` now sends `chat_template_kwargs.enable_thinking` for `nvidia/nemotron*` models, off by default, with `REASONING_ENABLE_THINKING` and `NON_REASONING_ENABLE_THINKING` to turn it on.

3. **Client choice by setting.** `_build_client` chose `ChatOpenAI` only for `openai/`, `azure/` and `aws/` model names. `REASONING_CLIENT`, `NON_REASONING_CLIENT` and `DEFAULT_MODELS_CLIENT` (`openai` or `nvidia`, through the existing `resolve()`) now override that, so any OpenAI-compatible endpoint, such as a model router, can serve a role. For Claude through such a route (`anthropic/` model names), structured output keeps LangChain's forced tool call; the `tool_choice=None` workaround stays for the `aws/` and `azure/` gateway.

4. **`calculation_only` on the chat API.** The agent already supports `calculation_only`; `ChatRequest` did not expose it. For a code map, questions such as "Which functions does X call?" read like questions about the catalog and were routed to the information agent. The flag lets a caller send them to SQL.

## Measured effect

Their own agent, asked 22 questions about Auto Ontology's source code (the code map in this repository), with `deepseek/deepseek-v4.1-flash-1017` through OpenRouter and NVIDIA embeddings. The full record is in [`../RESULTS.md`](../RESULTS.md).

| | Unpatched, `nemotron-3-nano` | Unpatched, `nemotron-3.5-lightning` | Patched, DeepSeek V4.1 Flash |
|---|---|---|---|
| Semantic compilation | model calls fail (`410`) | 663 s, 24 structured-output errors | about 30 s |
| Questions answered | 0 of 5 | 0 of 5 (first still running at 45 min) | 22 of 22 |
| Right content | 0 | 0 | 21 of 22 |

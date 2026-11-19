# copydesk — agent instructions

Multi-agent ad-copy pipeline (LangGraph) with a compliance gate and an eval harness.
Fictional brand: Acme Telehealth.

## Stack
- Python 3.12, uv, langchain v1, langgraph v1, langchain-anthropic, pydantic v2, pyyaml, pytest, ruff.
- Models via `init_chat_model`, IDs read from `.env` (per node). Never hardcode or guess model names.

## Architecture
- This is an explicit LangGraph workflow (StateGraph + Send). Don't use Deep Agents or create_agent:
  the fan-out and the rewrite limit are business rules, so they stay fixed edges.
- Compliance violations carry rule_id, span and fix_hint. On a rewrite the copywriter sees only:
  brief, angle, its draft, the violations.
- Count tokens with UsageMetadataCallbackHandler in the invoke config.
- report.html: one Meta-style ad card per variant with a status badge. Single file, no frameworks.

## Rules
- Use current LangChain v1 / LangGraph APIs. No `LLMChain`, no `langchain.schema`, no provider classes from `langchain.chat_models`
  (e.g. `from langchain.chat_models import ChatAnthropic`). `from langchain.chat_models import init_chat_model` is correct.
  If unsure about an API, check the LangChain docs MCP before writing code.
- Structured output: `with_structured_output(Model, method="json_schema")`. Don't set `temperature` (not supported on current Claude models).
- Every handoff between nodes is a Pydantic model. No free-form dicts across node boundaries.
- Parallel branches writing the same state key need a reducer.
- Compliance: deterministic checks (rules.yaml) first, LLM review second. rules.yaml is data only.
- Never weaken a check, regex, or eval threshold to make something pass. If it fails, explain why first.
- Evals call the real model. Unit tests may mock it.
- Eval code imports checks from `copydesk.rules`; never reimplement them.
- One agent per file; system prompts as module-level constants.
- Don't add features, dependencies, or files I didn't ask for. Suggest them in one line at the end instead.

## Commands
- Run:   `uv run python -m copydesk "<brief>"`
- Tests: `uv run pytest -q`
- Evals: `uv run python -m evals.run [--save-baseline | --compare results/baseline.json]`

## Done means
Tests green, the command actually ran, and you showed me the output.

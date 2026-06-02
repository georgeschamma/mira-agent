# MIRA Agent

Phase 1 MIRA app. The app preserves the validated FastAPI, Supabase Auth, org-scoped RLS, and runtime user-JWT database path, then adds the first real analysis workflow: brief -> LangGraph shell -> Exa research -> PydanticAI content recommendations -> persisted action sheet/audit rows.

## Local Setup

```bash
cp .env.example .env
uv sync
supabase start
supabase db reset
uv run python scripts/create_demo_users.py
make dev
```

`.env` must include local Supabase values plus:

```bash
LLM_PROVIDER=openai-compatible
LLM_MODEL=gpt-5.5
LLM_BASE_URL=https://api.freemodel.dev/v1
LLM_API_KEY=replace-with-runtime-llm-key
EXA_API_KEY=replace-with-exa-key
EXA_NUM_RESULTS=5
```

## Validate

```bash
make validate
```

`make validate` runs compile checks, Ruff, and the unit/API test suite. For local Supabase and end-to-end checks, run:

```bash
supabase start
supabase db reset
uv run python scripts/create_demo_users.py
make test-rls
make dev
make health
```

`make dev` starts `mira_agent.main:app` on port `8123`. Both health endpoints should return:

```json
{"status":"healthy"}
```

`/api/analyze` requires a Supabase Bearer JWT and an analyst/admin org role. Successful runs return sourced recommendations, create audit rows for `router`, `research`, and `content`, and create pending approval rows for high-impact recommendations.

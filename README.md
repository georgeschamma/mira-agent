# MIRA Agent

Phase 2 MIRA app. FastAPI serves the API and the React/Vite browser app from one service.
The product slice is: sign in with Supabase, submit a campaign brief, run the thin LangGraph
analysis, view the saved report, inspect audit rows, approve high-impact recommendations as
Admin, and export Markdown.

The graph remains narrow: router -> Exa research -> PydanticAI content recommendations.

## Local Setup

```bash
cp .env.example .env
uv sync
supabase start
supabase db reset
uv run python scripts/create_demo_users.py
make dev
```

The seed script writes `.demo.env` with fresh JWTs and `DEMO_PASSWORD`; the file is ignored by
Git and should stay local.

`.env` must include local Supabase values plus:

```bash
LLM_PROVIDER=openai-compatible
LLM_MODEL=gpt-5.5
LLM_BASE_URL=https://api.freemodel.dev/v1
LLM_API_KEY=replace-with-runtime-llm-key
EXA_API_KEY=replace-with-exa-key
EXA_NUM_RESULTS=5
```

Open `http://localhost:8123`, sign in with a seeded Analyst user, submit the brief form, then
view the report and audit tabs. Sign out and sign in as Admin to approve or reject pending
high-impact recommendations. Use Export Markdown from the report view.

The browser loads Supabase runtime config from `/api/config`; no `VITE_*` Supabase values are
required for Docker or Azure.

## Validate

```bash
make validate
cd ui && npm run build
```

For local Supabase and real-JWT checks:

```bash
supabase start
supabase db reset
uv run python scripts/create_demo_users.py
make test-rls
make dev
make health
```

`make dev` starts `mira_agent.main:app` on port `8123`. Health endpoints:

```bash
curl -fsS http://localhost:8123/health
curl -fsS http://localhost:8123/health/db
curl -fsS http://localhost:8123/api/config
```

## API Routes

- `GET /health`
- `GET /health/db`
- `GET /api/config`
- `POST /api/analyze`
- `GET /api/action-sheets/{action_sheet_id}`
- `GET /api/runs/{run_id}/audit`
- `POST /api/action-sheets/{action_sheet_id}/approvals/{recommendation_id}`

All report, audit, analyze, and approval request paths use the Supabase user JWT with the anon
key. The service-role key is restricted to migrations, seed scripts, and tests.

## Azure Smoke

Build the one-image app and deploy it to Azure Container Apps with runtime env vars and
`secretref:` values. See `ops/azure/README.md` for commands and the smoke checklist covering
health, DB health, UI login, analyze, report, audit, approval, and Markdown export.

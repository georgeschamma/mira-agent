# MIRA Agent

MIRA is a FastAPI + React/Vite media-plan agent served from one Docker image. Phase 2 remains
available as the shipped baseline, while Phase 3 adds the document-first media-plan path:
sign in with Supabase, submit a free-text brief plus CRM and GA4 CSVs, run the LangGraph media-plan
workflow, view the saved strategy document, inspect audit rows, approve the document as Admin, and
export Markdown.

Current runtime graph: router -> Exa research -> PydanticAI content recommendations.

Current Phase 3 runtime graph:

`brief -> research + audience + performance -> strategy`

Phase 3 budget allocation numbers come from deterministic `services/mmm.py` logic, not LLM prose.
See:

- `../.agents/plans/phase-3-media-plan-agent-mmm.md`
- `../.agents/plans/phase-3-media-plan-contract-lock.md`
- `../.agents/plans/phase-3-media-plan-implementation.md`

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

Open `http://localhost:8123`, sign in with a seeded Analyst user, submit the media-plan input
with CRM and GA4 CSV files, then view the report and audit tabs. The generated action-sheet ID is
retained when you sign out; sign in as Admin and the report reloads so you can approve or reject
the pending document approval. You can also load any RLS-visible report by action-sheet ID. Use
Export Markdown from the report view.
CRM and GA4 CSV uploads are capped at 2 MB each.

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

The RLS suite refuses to mutate a non-local Supabase project unless
`RUN_REMOTE_RLS_TESTS=1` is also set explicitly.

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
- `POST /api/media-plan`
- `POST /api/analyze`
- `GET /api/action-sheets/{action_sheet_id}`
- `GET /api/runs/{run_id}/audit`
- `POST /api/action-sheets/{action_sheet_id}/approvals/{recommendation_id}`

All report and audit reads plus route-level organization authorization use the Supabase user JWT
with the anon key so RLS applies. Generated campaign, run, action-sheet, approval, and audit writes
use the backend-only service-role key after user-JWT authorization. The service-role key is never
returned by `/api/config` or exposed to the browser.

## Azure Smoke

Build the one-image app with `.github/workflows/build-acr-image.yml`, then deploy it to Azure
Container Apps with runtime env vars and `secretref:` values. The workflow uses GitHub OIDC and a
least-privilege Azure identity, not stored registry credentials. See `ops/azure/README.md` for
commands and the smoke checklist covering health, DB health, UI login, media-plan submission,
report, audit, approval, and Markdown export.

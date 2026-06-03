# AGENTS.md - MIRA Agent App

Project-local rules for the generated MIRA app. These rules apply inside `mira-agent/`.

## Scope

- This app is Phase 2: a visible thin product slice over the Phase 1 FastAPI, Supabase Auth/RLS,
  and real analysis workflow.
- `/api/analyze` still runs the narrow sequential LangGraph shell: router -> Exa research ->
  PydanticAI content recommendations.
- The browser app signs in with Supabase email/password, submits a brief, reads the persisted
  report and audit trace, updates existing approval rows as Admin, and exports Markdown.
- Azure work is limited to one-image Container Apps deploy/smoke documentation and validation.
- Do not add CRM, GA4, full v1 graph nodes, eval suites, benchmarks, payments, public signup,
  Redis, Airflow, OpenSearch, vector RAG, or CRM writeback in this phase.
- Use one service: FastAPI serves API routes and the React/Vite static bundle.
- Runtime database reads/writes must use the user's Supabase JWT with the anon key. Never use
  the service-role key on request paths.
- Service-role use is allowed only for migrations, seed/demo user scripts, and test setup.

## Stack

- Python 3.11+
- FastAPI + Uvicorn
- Supabase Auth + Postgres + RLS
- Direct PostgREST calls through a small RLS-bound client
- LangGraph for the thin analysis workflow
- Exa for sourced research
- PydanticAI for structured content recommendations
- React + Vite product UI
- Supabase JS browser auth
- uv for Python dependencies
- pytest and ruff for validation

## Commands

```bash
cp .env.example .env
uv sync
supabase start
supabase db reset
uv run python scripts/create_demo_users.py
make dev
make health
make validate
make test
make test-rls
make lint
make ui-build
make build
make docker
```

## Architecture

```text
src/mira_agent/
+-- main.py
+-- config.py
+-- auth.py
+-- dependencies.py
+-- exceptions.py
+-- routers/
|   +-- health.py
|   +-- config.py
|   +-- analyze.py
|   +-- approvals.py
|   +-- reports.py
+-- graph/
|   +-- graph.py
|   +-- state.py
|   +-- context.py
|   +-- nodes/
+-- integrations/
|   +-- exa.py
|   +-- llm.py
+-- repositories/
|   +-- rls_client.py
|   +-- campaigns.py
|   +-- approvals.py
|   +-- reports.py
+-- schemas/
    +-- analyze.py
    +-- auth.py
    +-- errors.py
    +-- report.py
```

## Rules

- Keep `main.py` thin: app setup, middleware, exception handlers, routers, static mount only.
- Keep table operations inside `repositories/`.
- Every API error returns `{"error":{"code","message","request_id"}}`.
- Do not log JWTs, API keys, request bodies, CSV contents, CRM rows, or unredacted PII.
- Organization membership is the tenant boundary. Do not add global user roles.
- RLS policies must be created in migrations with the tables they protect.
- `/health` and `/health/db` are the canonical health endpoints.
- `/api/config` may expose only browser-safe values: app metadata, `SUPABASE_URL`, and
  `SUPABASE_ANON_KEY`.
- `/api/analyze` must preserve route-level org role checks before graph execution.
- Report and audit reads must use user-JWT-bound `RlsClient`; RLS-hidden rows should not leak
  cross-org existence.
- Admin approval must use the existing approval endpoint. Do not add a duplicate approval path.
- Every recommendation must have a concrete URL or `brief:*` source.
- Markdown export is client-side only in Phase 2.
- `make validate` is the canonical no-Supabase local validation target.
- Azure docs must use placeholders and `secretref:` for secrets.
- Update `app_structure_llm.txt` when routes, folders, infrastructure, or data flow change.

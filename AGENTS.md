# AGENTS.md - MIRA Agent App

Project-local rules for the generated MIRA app. These rules apply inside `mira-agent/`.

## Scope

### Active Phase 3 target

- MIRA's active product direction is now a media-plan agent:
  free-text brief + CRM CSV + GA4 CSV -> brief -> parallel research/audience/performance ->
  strategy document.
- Phase 3 implementation must work from an approved `.agents/plans/phase-3-*` plan.
- CRM and GA4 are in scope for approved Phase 3 work, but raw CSV contents must not be logged,
  exposed, or persisted unless a migration/RLS plan explicitly allows it.
- Budget allocation numbers must come from deterministic `services/mmm.py` logic. LLMs may write
  sourced narrative around fixed numbers, but must not invent spend allocations.
- The old analytics/creative/media/content six-domain graph is not the Phase 3 target.
- Add a document-first media-plan path while keeping shipped Phase 2 `/api/analyze`, report,
  audit, and approval behavior stable until retirement is explicit.
- Phase 3 runtime route is `POST /api/media-plan` with multipart fields `org_id`, `brief`,
  `crm_csv`, and `ga4_csv`; CRM and GA4 CSV uploads are capped at 2 MB each.
- Phase 3 graph is `brief -> research + audience + performance -> strategy`; do not revive the
  old analytics/creative/media/validation/content graph.

### Current shipped app

- This app is the live Phase 3 media-plan product, with the Phase 2 analysis route retained as a
  regression baseline.
- `/api/analyze` still runs the narrow sequential LangGraph shell: router -> Exa research ->
  PydanticAI content recommendations.
- The browser app signs in with Supabase email/password, submits a brief, reads the persisted
  report and audit trace, updates existing approval rows as Admin, and exports Markdown.
- Azure work is limited to one-image Container Apps deploy/smoke documentation and validation.
- Do not add eval suites, benchmarks, payments, public signup, Redis, Airflow, OpenSearch,
  vector RAG, or CRM writeback in this phase.
- Use one service: FastAPI serves API routes and the React/Vite static bundle.
- Runtime database reads and tenant/role authorization must use the user's Supabase JWT with the
  anon key so RLS applies.
- Generated campaign, run, action-sheet, approval, and audit writes must use the backend-only
  service-role client after route-level user-JWT authorization. Never expose the service-role key
  through `/api/config`, browser code, logs, or user-controlled requests.

## Stack

- Python 3.11+
- FastAPI + Uvicorn
- Supabase Auth + Postgres + RLS
- Direct PostgREST calls through a small RLS-bound client
- LangGraph for the thin analysis workflow
- Exa for sourced research
- PydanticAI for structured content recommendations
- NumPy/SciPy for approved Phase 3 deterministic media-plan allocation logic
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
|   +-- media_plan.py
+-- graph/
|   +-- graph.py
|   +-- state.py
|   +-- context.py
|   +-- nodes/
+-- integrations/
|   +-- exa.py
|   +-- llm.py
|   +-- ga4.py
|   +-- crm.py
+-- services/
|   +-- mmm.py
+-- repositories/
|   +-- rls_client.py
|   +-- campaigns.py
|   +-- approvals.py
|   +-- reports.py
|   +-- media_plans.py
+-- schemas/
    +-- analyze.py
    +-- auth.py
    +-- errors.py
    +-- report.py
    +-- media_plan.py
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
- `/api/media-plan` must verify Supabase auth and org role before graph execution; CSV files are
  capped at 2 MB each, parsed in memory, and raw contents must not be persisted.
- Report and audit reads must use user-JWT-bound `RlsClient`; RLS-hidden rows should not leak
  cross-org existence.
- Authenticated browser roles must not have direct insert/update/delete privileges on generated
  campaign, run, action-sheet, approval, or audit tables.
- RLS security-definer helper functions must live in a non-exposed schema.
- Admin approval must use the existing approval endpoint. Do not add a duplicate approval path.
- Every recommendation must have a concrete URL or `brief:*` source.
- Phase 3 document claims must use concrete `https://...`, `brief:*`, `crm:segment:*`,
  `ga4:*`, or `performance:*` sources.
- Markdown export is client-side only in Phase 2.
- `make validate` is the canonical no-Supabase local validation target.
- Azure docs must use placeholders and `secretref:` for secrets.
- GitHub Actions Azure authentication must use OIDC with least-privilege Azure roles. Do not add
  registry passwords or Azure client secrets to repository configuration.
- Reviewer samples must use synthetic data only. Never commit real CRM contacts or demo passwords.
- Update `app_structure_llm.txt` when routes, folders, infrastructure, or data flow change.

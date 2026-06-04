# Phase 3 Media Plan Implementation Report

## Meta Information

- Plan file: `../.agents/plans/phase-3-media-plan-implementation.md`
- Feature: Phase 3 media-plan agent
- Branch: `feat/phase-2-report-audit-ui`
- Date completed: 2026-06-04
- Lines changed: +3032 -161, excluding this execution report file

### Files Added

- `.agents/code-reviews/phase-3-media-plan-review.md`
- `src/mira_agent/graph/nodes/audience.py`
- `src/mira_agent/graph/nodes/brief.py`
- `src/mira_agent/graph/nodes/performance.py`
- `src/mira_agent/graph/nodes/strategy.py`
- `src/mira_agent/integrations/crm.py`
- `src/mira_agent/integrations/ga4.py`
- `src/mira_agent/repositories/media_plans.py`
- `src/mira_agent/routers/media_plan.py`
- `src/mira_agent/schemas/media_plan.py`
- `src/mira_agent/services/__init__.py`
- `src/mira_agent/services/mmm.py`
- `supabase/migrations/202606030001_media_plan_documents.sql`
- `tests/api/test_media_plan.py`
- `tests/unit/test_crm_integration.py`
- `tests/unit/test_ga4_integration.py`
- `tests/unit/test_media_plan_repository.py`
- `tests/unit/test_mmm.py`
- `tests/unit/test_performance_node.py`
- `tests/unit/test_strategy_node.py`

### Files Modified

- `AGENTS.md`
- `README.md`
- `app_structure_llm.txt`
- `ops/azure/README.md`
- `pyproject.toml`
- `src/mira_agent/graph/graph.py`
- `src/mira_agent/graph/state.py`
- `src/mira_agent/main.py`
- `src/mira_agent/repositories/reports.py`
- `src/mira_agent/schemas/report.py`
- `tests/unit/test_graph_flow.py`
- `ui/src/api.ts`
- `ui/src/main.tsx`
- `ui/src/reportMarkdown.ts`
- `ui/src/styles.css`
- `ui/src/types.ts`
- `uv.lock`

Workspace operational logs also changed outside this app repo:

- `/Users/georgeschamma/Library/CloudStorage/GoogleDrive-georgeschamma@gmail.com/My Drive/Claude/bugs.md`
- `/Users/georgeschamma/Library/CloudStorage/GoogleDrive-georgeschamma@gmail.com/My Drive/Claude/tasks/lessons.md`

## Validation Results

- Syntax & Linting: ✓ `uv run python -m compileall src tests scripts`, `uv run ruff check .`, and `git diff --check` passed.
- Type Checking: ✓ `npm run build` ran `tsc -b` successfully before Vite build.
- Unit Tests: ✓ 41 unit tests passed as part of `uv run pytest tests/unit tests/api`.
- API Tests: ✓ 13 API tests passed as part of `uv run pytest tests/unit tests/api`.
- Integration Tests: ⚠ Supabase local stack, `supabase db reset`, and demo-user seed passed; `RUN_RLS_TESTS=1 uv run pytest tests/integration/test_rls_real_jwt.py` ran but skipped because the local validation `.env` lacks live LLM and Exa keys.
- Full Local Validation: ✓ `make validate` passed after rerunning with filesystem permission for `uv` cache access.
- UI Build: ✓ `npm run build` passed.

## What Went Well

- Existing repository boundaries mapped cleanly to Phase 3: request paths still use user-JWT-bound `RlsClient`, and table writes stayed in `repositories/`.
- The deterministic media math stayed isolated in `services/mmm.py`, which made it straightforward to test allocation edge cases without LLM or network dependencies.
- GA4 and CRM parsing were implemented as small deterministic adapters with focused unit tests, including sparse data, protected CRM attributes, and invalid row warnings.
- The Phase 2 `/api/analyze` flow remained stable while the new `/api/media-plan` path was added alongside it.
- The React app could be updated without adding a separate frontend route or state framework; the existing compact product shell was enough.
- The pre-commit review caught two real issues before commit: unbounded upload reads and loose `http://` source validation. Both were fixed with regression tests.

## Challenges Encountered

- Local validation touched operator state. Generating `.env` from local Supabase made validation work, but it replaced any hosted Supabase values that may have been in the app-local `.env`.
- Several validation commands needed filesystem permission outside the workspace because `supabase` writes under `~/.supabase` and `uv` uses `~/.cache/uv`.
- The live/RLS integration test path is still not Phase 3-specific and skipped without live LLM/Exa keys. This leaves a live end-to-end gap despite strong unit/API coverage.
- LangGraph parallel state required reducer-backed fields. Without `Annotated[..., operator.add]`, branch outputs could be dropped, so the state shape had to be hardened before graph wiring.
- The strategy node needed a strict boundary between deterministic budget numbers and LLM-written narrative. Rendering the budget table in code avoided accidental LLM allocation drift.

## Divergences From Plan

### Upload Size Cap Added After Review

- Planned: Multipart route with `org_id`, `brief`, `crm_csv`, and `ga4_csv`; parse CSV files in memory.
- Actual: Added bounded chunk reads with a 2 MB cap per CSV and stable `MEDIA_PLAN_FILE_TOO_LARGE` 413 responses.
- Reason: Technical review identified unbounded `UploadFile.read()` as a resource-exhaustion risk for the single Azure Container App.
- Type: Security concern

### Source Validator Kept Inline

- Planned: Add document/source/PII validator shared by `strategy_node`.
- Actual: Source validation is currently implemented inline in `graph/nodes/strategy.py`; PII validation is enforced by the CRM parser and audit metadata rather than a separate shared validator module.
- Reason: There is one Phase 3 document writer today. A separate abstraction would not remove real duplication yet.
- Type: Better approach found

### Real-JWT Phase 3 Integration Not Completed

- Planned: Real-JWT media-plan flow with hosted/local Supabase when env is configured, including outsider read denial and Admin approval.
- Actual: Local Supabase reset and seed passed. Existing real-JWT integration command ran but skipped because live LLM/Exa keys were not present, and it is still oriented around the older live analysis path.
- Reason: The local validation `.env` intentionally contained only local Supabase values during this pass, and the existing integration test needs live AI/search configuration.
- Type: Plan assumption wrong

### Review Artifact Added

- Planned: Implementation and validation from the Phase 3 plan.
- Actual: Added `.agents/code-reviews/phase-3-media-plan-review.md` during the requested pre-commit review, then appended a resolution section after fixes.
- Reason: User requested a technical code review artifact before continuing.
- Type: Other

## Skipped Items

- Phase 3-specific real-JWT integration test was not added.
- Reason: The local environment lacked live LLM/Exa keys, and the current integration test harness is still centered on the Phase 2 `/api/analyze` flow.

- Live deployed smoke of `/api/media-plan` was not run.
- Reason: This implementation pass stopped at local validation. The hosted `.env` values and live LLM/Exa keys need to be restored before Azure smoke.

## Recommendations

- Plan command improvements: include a mandatory upload-security checklist for any multipart/file route: max bytes, chunked reads, too-large error code, and tests.
- Plan command improvements: require a Phase-specific integration test file whenever the plan introduces a new primary route, not just "integration tests" generically.
- Plan command improvements: add an environment-state step before Supabase validation: record whether `.env` points to local or hosted services and whether live AI/search keys are present.
- Execute command improvements: after `supabase start` or `uv` cache permission failures, rerun canonical validation with the approved escalation immediately and record the reason.
- Execute command improvements: run the technical review before final "ready for commit" status on high-risk changes, especially upload endpoints and auth/RLS paths.
- CLAUDE.md additions: add a standing rule that upload endpoints must enforce explicit byte caps and include regression tests in the same change.
- CLAUDE.md additions: add a reminder that local validation may rewrite `.env`; final reports must state whether hosted credentials need restoration before deploy smoke.

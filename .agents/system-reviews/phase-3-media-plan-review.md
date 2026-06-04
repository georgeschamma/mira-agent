# Phase 3 Media Plan System Review

## Meta Information

- Plan command reviewed: `.agents/workflows/feature-development/plan-feature.md`
  - Status: not found in this workspace or app repo.
- Generated plan reviewed: `../.agents/plans/phase-3-media-plan-implementation.md`
- Execute command reviewed: `.agents/workflows/feature-development/execute.md`
  - Status: not found in this workspace or app repo.
- Execution report reviewed: `.agents/execution-reports/phase-3-media-plan-implementation.md`
- Date: 2026-06-04
- Input note: The user did not pass `$1` or `$2` paths in this request, so this review used the
  known Phase 3 implementation plan and execution report from the current app repo.

## Overall Alignment Score: 8/10

The implementation followed the core architecture and delivery intent closely: new `/api/media-plan`
path, deterministic GA4/CRM/MMM boundaries, LangGraph Phase 3 flow, document persistence, React UI,
docs, and strong unit/API validation. The main process miss is that the plan's Phase 3-specific
real-JWT integration requirement did not become a concrete passing test. That is not a code bug in
this review, but it is a planning/execution gap because acceptance criteria said all validation
commands should pass and the integration path was underspecified for the new route.

## Planned Approach Summary

- Feature: document-first media-plan agent.
- Architecture: `free-text brief + CRM CSV + GA4 CSV -> brief -> research/audience/performance -> strategy document`.
- Backend: FastAPI multipart route with Supabase Auth, org-role check, RLS-bound repository writes.
- Graph: reducer-aware LangGraph state with parallel branch outputs.
- Deterministic logic: GA4 parsing, CRM aggregation, MMM budget allocation, budget table rendering.
- LLM role: sourced narrative only; no LLM-generated allocation numbers.
- Persistence: nullable document fields on `action_sheets`, document-level approval row through existing approvals path.
- UI: brief textarea, CRM/GA4 upload controls, saved document rendering, audit trace, Markdown export.
- Validation: compile, ruff, unit/API tests, UI build, Supabase reset, demo user seed, real-JWT integration, `make validate`, `make ui-build`.

## Actual Implementation Summary

- Implemented the new media-plan path and kept Phase 2 `/api/analyze` stable.
- Added deterministic CRM/GA4 parsers and MMM allocation logic with regression tests.
- Added Phase 3 graph state/nodes, route, repository, schemas, migration, UI, export, and docs.
- Added a pre-commit code review artifact and fixed its findings:
  - bounded CSV upload reads with a 2 MB per-file cap,
  - stricter `https://`/internal source validation.
- Validation passed locally for compile, ruff, unit/API tests, UI build, `make validate`, and `make ui-build`.
- Supabase local stack/reset/seed ran, but the existing real-JWT integration command skipped because live LLM/Exa keys were not present and the integration harness is not Phase 3-specific.

## Divergence Analysis

```yaml
divergence: Upload size cap added after review
planned: Multipart route parses CRM and GA4 CSV files in memory.
actual: Uploads are read in bounded chunks with a 2 MB per-file cap and MEDIA_PLAN_FILE_TOO_LARGE 413 errors.
reason: Technical review identified unbounded UploadFile.read() as a resource-exhaustion risk.
classification: good ✅
justified: yes
root_cause: plan validation missing upload security checklist
```

```yaml
divergence: Source validator kept inline
planned: Add document/source/PII validator shared by strategy_node.
actual: Source validation lives inline in strategy.py; PII guarantees are enforced by CRM parser and audit metadata.
reason: There is only one Phase 3 document writer; a shared validator module would be abstraction before reuse.
classification: good ✅
justified: yes
root_cause: plan over-specified abstraction shape instead of validation behavior
```

```yaml
divergence: Real-JWT Phase 3 integration not completed
planned: Real-JWT media-plan flow with local/hosted Supabase, outsider read denial, Analyst approval denial, and Admin approval.
actual: Supabase reset and seed passed; existing real-JWT integration command ran but skipped because live LLM/Exa keys were absent and the test still targets the older live analysis path.
reason: Local validation env intentionally had only local Supabase values, and live AI/search configuration was unavailable.
classification: bad ❌
justified: no
root_cause: validation missing concrete Phase 3 integration harness and env preflight
```

```yaml
divergence: Review artifact added
planned: Implementation and validation only.
actual: Added .agents/code-reviews/phase-3-media-plan-review.md and resolution notes.
reason: User requested a technical code review before continuing.
classification: good ✅
justified: yes
root_cause: user-added quality gate after implementation
```

```yaml
divergence: Workflow command files unavailable
planned: System review should read .agents/workflows/feature-development/plan-feature.md and execute.md.
actual: Those files were not present in the workspace/app repo, so review used the generated plan and execution report plus the user-provided command text from the conversation.
reason: Layer 1 workflow command assets are not checked into the project/workspace location referenced by the prompt.
classification: bad ❌
justified: no
root_cause: missing process assets
```

## Pattern Compliance

- [x] Followed codebase architecture
  - FastAPI router stayed thin, table writes stayed in repositories, RLS-bound client stayed on request paths.
- [x] Used documented patterns
  - Mirrored auth/org-role route pattern, report repository pattern, audit row pattern, and frontend API/type mirroring.
- [x] Applied testing patterns correctly
  - Added focused unit/API tests for parsers, math, graph nodes, repositories, route behavior, and review regressions.
- [~] Met validation requirements
  - Local syntax/lint/unit/API/UI validation passed.
  - Phase 3-specific real-JWT integration validation did not pass because it was not concretely implemented/configured.

## System Improvement Actions

### Update CLAUDE.md

- [ ] Add upload endpoint rule:

```markdown
When adding any upload endpoint, define an explicit per-file byte limit in the same change.
Read uploads in bounded chunks, return a stable too-large error, document the limit, and add a
regression test. Never call `UploadFile.read()` without a size guard on request paths.
```

- [ ] Add environment-state rule:

```markdown
Before local or hosted validation writes `.env` or `.demo.env`, record whether the app is pointed
at local or hosted services. Final reports must state when hosted credentials/LLM/search keys need
to be restored before deploy smoke.
```

- [ ] Add integration-test specificity rule:

```markdown
When a new primary API route is introduced, add or update an integration test for that route.
Do not count an older route's integration test as coverage for the new product path.
```

### Update Plan Command

- [ ] Add an "Upload/Input Safety" section to generated plans:

```markdown
If the feature accepts files or large text input, specify:
- max accepted size,
- streaming/chunked read strategy,
- stable error code/status for too-large input,
- tests for oversized input,
- whether raw input can be logged or persisted.
```

- [ ] Add an "Environment Preflight" section before validation:

```markdown
List required env groups separately:
- local database/auth,
- hosted database/auth,
- live network integrations,
- fake/test-only substitutions.
State which validation commands require each group and what should happen if a group is missing.
```

- [ ] Change "Integration Tests" from broad prose to concrete commands and files:

```markdown
For every new API route, name the exact integration test file to create or update and the exact
command that must pass. If live dependencies are required, define a fake-dependency integration
alternative that still exercises auth/RLS boundaries.
```

### Create New Command

- [ ] `/preflight-env` for environment-state auditing.
  - Purpose: print local/hosted Supabase target, required live AI/search key presence, `.demo.env`
    age, and which validation levels can run.
  - Reason: Env confusion repeated across Phase 2/3 validation and deployment smoke.

- [ ] `/review-upload-route` for upload endpoint safety.
  - Purpose: scan changed FastAPI routes for `UploadFile`, unbounded `.read()`, missing size
    tests, and undocumented upload limits.
  - Reason: Upload security was caught manually in review and should become automated.

### Update Execute Command

- [ ] Add a mandatory pre-edit check for `bugs.md`, and a post-fix update to `tasks/lessons.md`.
  - This is already a workspace rule, but execution command should enforce it explicitly.

- [ ] Add "run a technical review before final ready-for-commit" for high-risk feature classes:
  - auth/RLS,
  - file uploads,
  - payment/security,
  - deployment/runtime secrets,
  - data migrations.

- [ ] Add validation fallback handling:

```markdown
If a validation command skips because env is missing, classify the skipped acceptance criterion:
- acceptable local skip,
- must-run before deploy,
- missing test harness that must be added now.
Do not report "all validation passed" when an acceptance criterion skipped.
```

- [ ] Add a command-file availability check:

```markdown
At the start of system review, verify the referenced plan/execute workflow files exist. If missing,
record this as a process asset gap and recommend where to store them.
```

## Key Learnings

### What Worked Well

- The generated plan had strong architectural boundaries: deterministic math, RLS-bound writes,
  Phase 2 stability, and source/PII constraints.
- Keeping the output as a document-first media plan prevented the old six-domain graph from
  reappearing.
- Focused unit/API tests gave fast feedback and caught review fixes cleanly.
- The execution report captured divergences honestly, which made this system review actionable.

### What Needs Improvement

- Integration validation needs to be route-specific and env-aware. "Run integration tests" is not
  enough when the existing integration test targets a previous product path.
- Upload/file safety should be in planning, not discovered during code review.
- Workflow command files referenced by the system-review prompt should be committed or otherwise
  discoverable; absent Layer 1 assets weaken the review.
- Validation summaries need a distinct status for "skipped because env missing" so skipped
  acceptance criteria cannot be mistaken for passed checks.

### For Next Implementation

- During planning, include a route-by-route validation matrix: unit, API, RLS/integration, UI,
  live smoke.
- Before execution, run `/preflight-env` or equivalent and record whether local, hosted, and live
  network validations are possible.
- Before final commit readiness, run a technical review for any auth/RLS/upload/migration feature
  and fix findings before generating the execution report.
- Store reusable workflow command files under the project or workspace `.agents/workflows/` path
  referenced by prompts, so future system reviews can evaluate process definitions directly.

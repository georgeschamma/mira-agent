# MIRA Agent Full Technical Review

Review scope: full tracked `main` HEAD at `9828805` (`feat: ship MIRA report UI and Phase 3 media plan agent`). The worktree was clean before this review.

**Stats:**

- Files Modified: 0
- Files Added: 0
- Files Deleted: 0
- New lines: 0
- Deleted lines: 0

## Findings

severity: critical
file: supabase/migrations/202606020001_core_org_rls.sql
line: 211
issue: Browser-authenticated Analysts can forge trust-sensitive audit rows directly through PostgREST
detail: The browser receives the Supabase URL, anon key, and user JWT, while the RLS policies allow Analysts and Admins to insert campaigns, campaign runs, action sheets, approvals, and audit rows. Because the backend uses the same authenticated user authority, RLS cannot distinguish a backend-generated audit row from one fabricated by the browser. A local verification using an Analyst JWT received HTTP 201 for direct campaign, run, and `audit_log` inserts, which undermines the audit trace as evidence.
suggestion: Separate backend write authority from browser authority. Revoke direct authenticated inserts on trust-sensitive tables and route writes through backend-only database functions or a backend-specific claim/role while preserving tenant checks for reads.

severity: critical
file: supabase/migrations/202606020001_core_org_rls.sql
line: 112
issue: Public security-definer RLS helper functions leak cross-organization row existence
detail: `campaign_org` and `action_sheet_org` are created in the exposed `public` schema as `security definer` functions without revoking public execution. An outsider JWT can call these functions through PostgREST RPC even when RLS hides the underlying rows. A local verification called `rpc/campaign_org` with an outsider JWT and received HTTP 200 plus the other tenant's organization ID, violating the documented rule that RLS-hidden rows must not leak cross-org existence.
suggestion: Move RLS helper functions into a non-exposed private schema, restrict execute privileges, and add a real-JWT regression test proving outsider RPC calls cannot reveal tenant identifiers.

severity: high
file: ui/src/main.tsx
line: 129
issue: The documented Analyst-to-Admin approval workflow cannot be completed in the React UI
detail: Signing out clears the only loaded report and audit state. The UI only calls `getActionSheet` immediately after the current user submits a media plan, and it has no organization report history or load-by-ID control. Therefore an Admin who signs in after an Analyst run sees "No report loaded" and cannot approve the Analyst-created document, despite the README instructing this exact handoff.
suggestion: Add an organization-scoped report list or load-by-ID flow, preserve the selected action-sheet ID across the account handoff, and add a browser test for Analyst run followed by Admin approval.

severity: high
file: src/mira_agent/graph/nodes/strategy.py
line: 115
issue: Strategy LLM fallback is recorded as a successful high-confidence model result
detail: Any strategy model failure returns `fallback_narrative` without adding an error marker. The subsequent audit row uses the configured model name, assigns high confidence when the prior state has no errors, and marks the campaign run `done`. A forced model failure produced `confidence=high`, `model_used=test-model`, and `run_status=done`, so the audit trace misrepresents fallback content as model-backed output.
suggestion: Record a strategy fallback `NodeError`, mark the run partial, attribute the output to a clear fallback marker instead of the configured model, and lower the audit confidence.

severity: high
file: src/mira_agent/graph/nodes/brief.py
line: 66
issue: Missing Budget fields can silently use an unrelated number as the media-plan budget
detail: When no explicit `Budget:` field exists, the parser searches the entire free-text brief and uses the first number found. The brief `Product: MIRA 2.0` with no budget parsed as budget `2`, which can drive materially incorrect deterministic spend recommendations instead of falling back to current GA4 spend.
suggestion: Parse budget only from explicit budget fields or well-defined currency patterns. If no budget is present, return zero/current-spend fallback and add a warning.

severity: medium
file: src/mira_agent/graph/nodes/strategy.py
line: 24
issue: Unsourced strategy narrative can pass validation with an empty claims list
detail: `StrategyNarrativeOutput.claims` defaults to an empty list, and `validate_source_claims` only checks entries that exist. A narrative with five populated prose sections and zero claims validates and renders an empty Sources & Audit section, despite the Phase 3 source contract.
suggestion: Require at least one claim with Pydantic length constraints, reject empty claims after model output validation, and ensure each rendered narrative section is supported by a source claim.

severity: medium
file: src/mira_agent/integrations/ga4.py
line: 184
issue: GA4 numeric parsing accepts NaN and Infinity values
detail: `_positive_float` rejects only values below zero, so Python's `float("NaN")` and `float("Infinity")` pass. A GA4 row with `NaN` cost reached `current_spend` and `ChannelPerformanceSummary.total_cost` as `nan`, which can poison fitting/allocation logic and cross JSON response boundaries.
suggestion: Reject non-finite values with `math.isfinite`, emit a row warning, and add tests for NaN, positive infinity, and negative infinity.

severity: medium
file: src/mira_agent/services/mmm.py
line: 296
issue: Allocation caps can leave requested budget silently unallocated
detail: The optimizer stops when every channel is at its cap or has non-positive marginal ROI, but returns the original `total_budget` without exposing the remaining amount. A $1,000 plan with two channels at $100 current spend and the default 2x cap returned recommendations totaling only $400, making the saved fixed-budget plan appear complete when $600 is unallocated.
suggestion: Expose and display unallocated budget with a warning, or explicitly define a fallback that allocates the remainder when the product contract requires full budget conservation.

severity: medium
file: src/mira_agent/repositories/approvals.py
line: 37
issue: Document approval updates leave action_sheets.document_status stale
detail: The approval path updates only `action_sheet_approvals`, while Phase 3 action sheets persist a separate `document_status` field that supports `approved` and `rejected`. After a document approval, API consumers can observe an approved approval row alongside `document_status="pending"`; the React UI masks this inconsistency by preferring the approval row.
suggestion: Update the document status together with the document approval in one database operation, or remove the duplicate status field and derive it consistently.

severity: medium
file: src/mira_agent/main.py
line: 31
issue: FastAPI request validation errors bypass the documented stable error envelope
detail: The app registers handlers for `ApiError` and generic exceptions but not `RequestValidationError`. With auth dependencies overridden, an empty `/api/analyze` request returned HTTP 422 with FastAPI's default `{"detail": [...]}` body instead of `{"error":{"code","message","request_id"}}`. The React client consequently shows only a generic HTTP 422 message.
suggestion: Register a safe request-validation handler that returns the stable MIRA error envelope and add API tests for invalid JSON and multipart fields.

severity: low
file: tests/integration/test_rls_real_jwt.py
line: 18
issue: The real-JWT RLS test can skip all RLS coverage and does not cover the Phase 3 route
detail: The test skips before exercising Supabase unless live LLM and Exa keys are configured, and its only workflow request is `/api/analyze`. During this review, `make test-rls` exited successfully with one skipped test, so Phase 3 media-plan RLS, document approval, and audit behavior are not protected by an automated real-JWT check.
suggestion: Split RLS/auth persistence checks from live external integrations, use deterministic graph dependencies where appropriate, and add `/api/media-plan` real-JWT coverage.

## Validation Evidence

- `make validate`: passed, 54 unit/API tests passed.
- `make ui-build`: passed.
- `git diff --check HEAD`: passed.
- `npm audit --omit=dev`: passed, 0 vulnerabilities.
- `RUN_RLS_TESTS=1 uv run pytest tests/integration/test_rls_real_jwt.py`: exited successfully with 1 skipped test.
- Targeted reproductions confirmed budget parsing, non-finite GA4 acceptance, allocation non-conservation, default 422 response shape, empty strategy claims, strategy fallback audit misattribution, direct Analyst audit insertion, and outsider helper-RPC leakage.

## Resolution

All findings are fixed, deployed, and verified from branch `fix/full-review-findings`.

- Generated records now use backend-only write authority after user-JWT RLS authorization. Authenticated browser writes are revoked, RLS helper functions are private, and a real-JWT security regression test proves Analysts cannot forge audit rows or call the helper RPC.
- The React UI preserves an action-sheet ID across the Analyst-to-Admin handoff and supports load-by-ID. Approval and document status now update atomically.
- Strategy fallback attribution, source claims, budget parsing, GA4 finite-value checks, unallocated budget reporting, and stable request-validation errors have focused regression coverage.
- The real-JWT harness refuses non-local Supabase mutation unless `RUN_REMOTE_RLS_TESTS=1` is set,
  and its setup rows are removed from a `finally` block.
- Validation passed: `make validate` with 64 tests, `make ui-build`, `git diff --check HEAD`,
  `npm audit --omit=dev`, a clean local Supabase migration reset, and the independent local and
  hosted real-JWT security tests.
- GitHub Actions built `miraphase2ocxng.azurecr.io/mira-agent:phase-3-3f5e998-amd64` with OIDC and
  a least-privilege `AcrPush` identity. Azure Container Apps revision
  `mira-agent-phase-2--0000005` is healthy and serving 100% of traffic.
- Hosted migration `202606040001_secure_backend_writes.sql` is applied. Live smoke tests passed
  for direct-write denial, private helper RPCs, tenant isolation, Analyst approval denial, Admin
  approval with persisted document status, stable validation errors, and an end-to-end media-plan
  report with per-agent audit rows.

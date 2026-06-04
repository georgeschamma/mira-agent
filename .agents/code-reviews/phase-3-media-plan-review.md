# Phase 3 Media Plan Technical Code Review

**Stats:**

- Files Modified: 17
- Files Added: 19
- Files Deleted: 0
- New lines: 2945
- Deleted lines: 161

## Findings

severity: critical  
file: src/mira_agent/routers/media_plan.py  
line: 52  
issue: Multipart CSV uploads are read fully into memory without a size limit.  
detail: `_read_upload_text()` calls `await upload.read()` for both CRM and GA4 files, and there is no route-level or shared upload limit in the app. An authenticated org member can submit arbitrarily large files and force the FastAPI worker/container to buffer them before parsing rejects anything. This is a practical resource-exhaustion risk for a single Azure Container App instance. Verified by searching the changed app code for upload/content-length guards; only this unbounded read path exists.  
suggestion: Enforce a small explicit max size per CSV before decoding, preferably by reading chunks up to a cap and returning a stable `MEDIA_PLAN_FILE_TOO_LARGE` error. Also document the accepted CSV size in the API contract/tests.

severity: medium  
file: src/mira_agent/graph/nodes/strategy.py  
line: 15  
issue: Source-claim validation accepts `http://` sources despite the Phase 3 contract requiring `https://` or internal refs.  
detail: `ALLOWED_SOURCE_PREFIXES` includes `http://`, but `AGENTS.md` says Phase 3 document claims must use `https://...`, `brief:*`, `crm:segment:*`, `ga4:*`, or `performance:*` sources. I verified the current validator accepts `http://example.com` with `validate_source_claims(...)`, so insecure external claim sources can enter generated documents instead of being rejected or forced through fallback.  
suggestion: Remove `http://` from `ALLOWED_SOURCE_PREFIXES`, update the agent instruction string to match exactly, and add a unit test asserting `http://` claims raise `ValueError`.

## Verification

```bash
git status
git diff HEAD
git diff --stat HEAD
git ls-files --others --exclude-standard
uv run python -c "from mira_agent.graph.nodes.strategy import validate_source_claims; from mira_agent.schemas.media_plan import SourceClaim; validate_source_claims([SourceClaim(claim='x', source='http://example.com')]); print('accepted')"
uv run pytest tests/api/test_media_plan.py tests/unit/test_strategy_node.py
git diff --check
```

Results:

- Required git inspection commands completed.
- Targeted source validation check printed `accepted`, confirming the `http://` mismatch.
- Targeted tests passed: `4 passed`.
- `git diff --check` passed.

## Resolution

Fixed on 2026-06-04:

- Added bounded chunk reads for `/api/media-plan` CSV uploads with a 2 MB per-file cap and
  `MEDIA_PLAN_FILE_TOO_LARGE` 413 errors.
- Removed `http://` from Phase 3 strategy source claim prefixes and added a regression test.
- Verified with targeted tests, full unit/API tests, UI build, and `make validate`.

**Stats:**

- Files Modified: 16
- Files Added: 11
- Files Deleted: 0
- New lines: 2239
- Deleted lines: 59

**Context Reviewed:**

- No `CLAUDE.md`, `/core`, or `/docs` directory exists in this repo.
- Read `AGENTS.md`, `README.md`, `pyproject.toml`, `src/mira_agent/config.py`,
  `src/mira_agent/dependencies.py`, auth/approval/campaign repository patterns, and the RLS
  migration.
- Ran `git status`, `git diff HEAD`, `git diff --stat HEAD`, and
  `git ls-files --others --exclude-standard`.
- Read every modified and untracked file in full.

**Validation Run:**

- `make validate` passed: compileall, Ruff, and 21 unit/API tests.
- `cd ui && npm run build` passed.
- Verified Docker runtime behavior with `docker run --rm --entrypoint uv mira-agent:phase-2 run python -c 'print("runtime-ok")'`.
- Verified route behavior for unsafe recommendation IDs with `uv run python` + `TestClient`.
- Verified exposed demo credentials in local `ui/dist` and the deployed Azure JS bundle.

severity: critical
file: ui/src/main.tsx
line: 25
issue: Demo Admin credentials are shipped in the browser bundle.
detail: A hardcoded `DEMO_PASSWORD` value was bundled with `analyst@mira.local` and
`admin@mira.local` account selectors. I verified the password and Admin email are present in
`ui/dist/assets/index-ClV8vQ5n.js` and in the deployed Azure JS bundle. Anyone with the public
Azure URL can click Admin, sign in, approve/reject recommendations, and run live analysis that
uses paid/limited external providers. This is an exposed credential and should be treated as
compromised.
suggestion: Remove password prefill from the client. Keep demo account email shortcuts if useful,
but require the password to be supplied out of band. Rotate the demo password after removing it
from the bundle. If auto-login is needed for demos, gate it behind a server-side dev/demo-only
mechanism that is disabled for public deployments.

severity: high
file: Dockerfile
line: 17
issue: Production container re-syncs/builds dependencies at startup.
detail: The image runs `uv run uvicorn ...` as its CMD. Even though the Dockerfile already runs
`uv sync --no-dev --no-editable`, `uv run` performs a runtime sync. Verified locally: the
production image printed `Building mira-agent @ file:///app`, downloaded `ruff`, uninstalled the
non-editable package, and installed dev-related packages before running the command. Azure logs
showed the same startup work. This makes cold starts slower and can fail when runtime egress or
package index access is unavailable.
suggestion: Run the already-created virtualenv directly. For example, set
`ENV PATH="/app/.venv/bin:$PATH"` and use
`CMD ["uvicorn", "mira_agent.main:app", "--host", "0.0.0.0", "--port", "8123"]`, or use
`uv run --no-sync ...` if you want to keep `uv` in the entrypoint. Rebuild and verify the
container starts without downloading/building packages.

severity: medium
file: src/mira_agent/graph/nodes/content.py
line: 210
issue: Model-generated recommendation IDs are not normalized to URL-safe path segments.
detail: Recommendation IDs come from LLM output and `_normalize_recommendation_id` only strips
whitespace and handles duplicates. The approval API uses `recommendation_id` as a path segment,
and `ui/src/api.ts` interpolates it directly into
`/api/action-sheets/{actionSheetId}/approvals/{recommendationId}`. I verified that a slash in the
ID causes the FastAPI route not to match; both `/rec/a` and encoded `%2F` variants fell through
to the static mount and returned 405. A model-produced ID containing `/` would make Admin
approval impossible for that recommendation.
suggestion: Normalize recommendation IDs server-side to a constrained URL-safe format such as
`[A-Za-z0-9_-]+` inside `_normalize_recommendation_id`, replacing other characters with `_`.
Add a unit test with an ID like `rec/high impact` and verify the approval endpoint can update the
persisted row. Encoding in the UI is still useful for ordinary reserved characters, but the
backend should not persist slash-containing IDs for a path-based API.

severity: medium
file: ops/azure/README.md
line: 66
issue: Azure deploy docs include the Supabase service-role key in app secrets by default.
detail: The create command stores `supabase-service-role-key="<SUPABASE_SERVICE_ROLE_KEY>"` in
the Container App secret set even though the running app does not need it and request paths must
use user JWTs with the anon key. This unnecessarily places a highly privileged database/auth key
inside the app resource configuration and broadens the blast radius of any Azure app config
access.
suggestion: Remove `supabase-service-role-key` from the default Container App create command.
Keep service-role use limited to migrations and seed scripts run from a trusted operator
environment. If Azure one-off admin jobs are later required, document a separate explicit command
that adds the secret only for that job and removes it afterward.

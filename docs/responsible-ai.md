# Responsible AI

MIRA is designed as an analyst-assist workflow for media planning. It drafts sourced strategy
documents and audit trails; it does not autonomously change campaigns or spend money.

## Decision Boundaries

- No autonomous ad-platform changes. MIRA does not publish campaigns, edit bids, change budgets,
  or write back to Google Ads, Meta, TikTok, LinkedIn, HubSpot, or GA4.
- No causal claims. Budget allocation is a deterministic saturation-curve heuristic and policy
  layer, not causal MMM or incrementality proof.
- No raw PII in outputs. CRM CSV rows are parsed in memory and reduced to aggregate segments.
- No unsupported provenance. Strategy claims must reference the run's actual source whitelist:
  brief fields, CRM/GA4 aggregate references, deterministic allocation outputs, or live research
  URLs.
- No approval bypass. Analyst users can generate plans, but Admin users approve or reject the
  retained document.

## Human In The Loop

The browser user authenticates through Supabase. FastAPI verifies the JWT and checks organization
membership before running the graph. Generated campaign, run, audit, and action-sheet writes use a
backend-only service-role client only after that user-JWT authorization succeeds.

The approval boundary is explicit:

- Analyst: can generate a media plan and view RLS-visible reports.
- Analyst: cannot approve generated recommendations or documents.
- Admin: can approve or reject the saved document for the same organization.
- Outsider tenant: cannot read or approve another organization's rows.

## Failure Modes

| Failure mode | Behavior |
|---|---|
| Strategy narrative contradicts deterministic allocation | Critic flags the issue and triggers one retry. |
| Strategy still fails provenance or consistency checks | Deterministic fallback narrative is saved with valid source references. |
| LLM provider unavailable or malformed | The run degrades to a structurally valid partial report where deterministic artifacts exist. |
| Research provider returns sparse or empty results | The report uses brief, CRM, GA4, and deterministic allocation references; research gaps remain visible. |
| Unsupported source reference appears in model output | Source whitelist validation rejects it before the document is saved. |
| Browser tries direct generated-record writes | Supabase grants/RLS deny the write. |
| Analyst attempts approval | API returns an approval-forbidden error. |

## PII Handling

CRM uploads are synthetic in the reviewer package. In runtime behavior, CSV contents are read in
memory, aggregate segment counts are produced, and raw CRM rows/emails are not persisted in reports
or audit rows. Audit rows mark the audience node with `pii_accessed=true` because CRM-derived input
was processed, while downstream strategy content receives aggregate segment labels only.

Secrets stay server-side. `/api/config` returns only browser-safe values and never returns the
Supabase service-role key, LLM key, Exa key, demo password, or JWTs.

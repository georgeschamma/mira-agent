# MIRA Demo Recording Script

Target length: 2 to 3 minutes.

## Before Recording

- Open the live app in a clean browser.
- Have the private demo password ready.
- Have `samples/crm-demo.csv` and `samples/ga4-demo.csv` ready for upload.
- Start signed out.

## 0:00-0:20 - Product And Inputs

Say:

> MIRA is a marketing intelligence agent that turns a campaign brief, CRM data, and GA4
> performance history into a sourced media plan.

Sign in as `analyst@mira.local`. Show the prefilled brief and upload both sample CSV files.

## 0:20-1:10 - Run The Agent

Run the media plan.

Trim or speed up the provider wait in the final recording if generation takes longer than the
target video length.

Say:

> The Brief Agent starts the run, then Research, Audience, and Performance work in parallel.
> Performance uses deterministic response-curve math for budget allocation. The LLM writes only
> the supporting sourced narrative.

When the report loads, show the strategy document and budget allocation table.

## 1:10-1:45 - Auditability

Open the Audit Trace tab.

Say:

> Every agent writes an audit row with its source, confidence, model, and step index. CRM output is
> aggregate only, and the uploaded raw rows are not persisted.

Show the fixed order: `brief`, `research`, `audience`, `performance`, `strategy`.

## 1:45-2:20 - Human Approval

Sign out and sign in as `admin@mira.local`. The selected action-sheet ID remains available and the
report reloads.

Say:

> Analysts can generate plans but cannot approve them. An Admin reviews the same saved document
> and approves or rejects it through the backend.

Approve the document and show the updated status.

## 2:20-2:40 - Export And Close

Export the Markdown report.

Say:

> MIRA is deployed as one Docker image on Azure Container Apps, with Supabase Auth, row-level
> security, backend-only trusted writes, and a reviewer-visible audit trail.

# MIRA Evidence Exports

This directory is for reviewer-safe smoke outputs:

- generated media-plan Markdown exports
- audit-trace JSON exports
- short smoke summaries

Do not store passwords, JWTs, Supabase service-role keys, LLM keys, Exa keys, or raw CRM contacts
here. Use `scripts/remote_smoke_test.py` to create timestamped exports from the Azure app.

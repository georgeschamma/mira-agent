# Security Policy

## Supported Versions

This repository is an open-source reference implementation. Security fixes are applied to the
default branch.

## Reporting a Vulnerability

Do not open a public issue for a vulnerability that could expose data, credentials, or
infrastructure. Report it privately through GitHub's private vulnerability reporting for this
repository when available, or contact the maintainer directly.

Include:

- Affected route, component, migration, or workflow.
- Reproduction steps with synthetic data only.
- Expected impact.
- Whether credentials, tenant isolation, generated reports, or external API spend are involved.

## Security Notes

- Never commit `.env`, `.demo.env`, JWTs, service-role keys, LLM keys, Exa keys, cloud credentials,
  or real customer data.
- Browser code may receive only publishable Supabase configuration. Backend-only service-role,
  LLM, and search provider keys must stay in runtime secrets.
- Keep Supabase Row Level Security enabled for every table that stores tenant-scoped data.
- Treat demo users as disposable. Rotate demo passwords before public demos and remove them when a
  demo is no longer needed.

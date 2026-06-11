# Reviewer Demo Data

These synthetic CSV files exercise the complete MIRA media-plan workflow without using real
customer data:

- `crm-demo.csv`: fictional contacts and allowed firmographic fields only.
- `ga4-demo.csv`: eight spend/response observations for Paid Search and Paid Social.

Use this brief for the $1,000 baseline scenario:

```text
Product: MIRA
Audience: B2B marketers
Channels: linkedin, paid search
Budget: 1000
Goal: book demos
```

Use this brief for the $10,000 growth & expansion scenario:

```text
Product: MIRA
Audience: B2B marketers
Channels: google, linkedin, meta, tiktok
Budget: 10000
Goal: grow pipeline
```

The CRM parser aggregates segments and does not return raw emails. The GA4 parser uses
`total_revenue` as the response when it is positive, otherwise it falls back to `conversions`.
Uploaded CSV contents are parsed in memory and are not persisted.

The live run can take 1 to 3 minutes because MIRA calls external research and narrative providers.

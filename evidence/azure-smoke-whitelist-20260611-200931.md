# Media Plan - MIRA

## Executive Summary
Brief budget is 10,000 versus current GA4 spend of 1,980, so the plan must increase capacity by 8,020.

## Budget Context
- Brief budget: 10,000
- Current GA4 spend: 1,980
- Net budget change required: 8,020 increase available
- Expansion budget available: 8,260
- Policy adjustments: Created expansion budget of 8,260 for channels: meta, tiktok.; Expansion allocation for meta: base weight 1.0 = weight 1.0; phase 1 3,300, staged reserve 200.; Expansion allocation for tiktok: base weight 1.0 = weight 1.0; phase 1 3,300, staged reserve 200.
- GA4 channels with performance data: 2 (Paid Search / google/cpc, Paid Social / linkedin/paid)
- Fitted allocation rows: 2 (Paid Search / google/cpc, Paid Social / linkedin/paid)
- Saturated fitted channels: Paid Search / google/cpc, Paid Social / linkedin/paid
- Brief channels without GA4 data: meta, tiktok
- Budget warnings: 8,260 of the requested budget was left unallocated because fitted channels reached supported spend caps.

## Budget Allocation
| Channel | Current Spend | Recommended Spend | Delta | Zone | Marginal ROI |
|---|---:|---:|---:|---|---:|
| Paid Search / google/cpc | 1,100 | 1,100 | 0 | saturated | 0.082 |
| Paid Social / linkedin/paid | 880 | 640 | -240 | saturated | 0.049 |

## Recommended Tests
| Channel | Phase-1 monthly test budget | Staged reserve | Hypothesis | Primary KPI | Source |
|---|---:|---:|---|---|---|
| meta | $3,300 | 200 | Test meta with controlled prospecting to prove qualified demand before releasing staged reserve. | Qualified leads; CAC | https://www.brandbearmarketing.com/post/what-is-a-good-cost-per-lead-b2b-benchmarks-by-industry |
| tiktok | $3,300 | 200 | Test tiktok with controlled prospecting to prove qualified demand before releasing staged reserve. | Qualified leads; CAC | https://syntermedia.ai/blog/best-performance-marketing-platforms-b2b |

Reserve pool: 1,260 held until phase-1 tests clear KPI gates.

## Audience Strategy
Industry: SaaS: 7 records (crm:segment:industry:saas) Company Size: 51-200: 5 records (crm:segment:company_size:51-200) Lifecycle Stage: lead: 5 records (crm:segment:lifecycle_stage:lead) Company Size: 201-500: 4 records (crm:segment:company_size:201-500) Industry: Services: 4 records (crm:segment:industry:services)

## Channel Rationale
Paid Search / google/cpc: 1,100 -> 1,100 (0, saturated, marginal ROI 0.082). Paid Social / linkedin/paid: 880 -> 640 (-240, saturated, marginal ROI 0.049).

## Expansion Opportunities
Created expansion budget of 8,260 for channels: meta, tiktok. Expansion allocation for meta: base weight 1.0 = weight 1.0; phase 1 3,300, staged reserve 200. Expansion allocation for tiktok: base weight 1.0 = weight 1.0; phase 1 3,300, staged reserve 200.

## Sequencing & Timing
Launch deterministic channel moves first, then review measured tests.

## Risks & Assumptions
8,260 of the requested budget was left unallocated because fitted channels reached supported spend caps. No deterministic allocation is available for meta, tiktok until GA4 spend history exists.

## Sources & Audit
- Budget moves come from deterministic performance allocation. (performance:allocation)
- Research signal: What Is a Good Cost Per Lead? B2B Benchmarks by Industry (https://www.brandbearmarketing.com/post/what-is-a-good-cost-per-lead-b2b-benchmarks-by-industry)
- Research signal: LinkedIn Ads for B2B Lead Generation: The 2026 Guide (https://generateleads.online/linkedin-ads-b2b-lead-generation-2026/)
- Research signal: SaaS Marketing in MENA: From Demo to Deal with AI | Hovi Digital Lab (https://thehovi.com/blog/industry-guides/saas-marketing-mena-demo-to-deal-with-ai)
- Audience priority: Industry: SaaS (crm:segment:industry:saas)
- Audience priority: Company Size: 51-200 (crm:segment:company_size:51-200)
- Audience priority: Lifecycle Stage: lead (crm:segment:lifecycle_stage:lead)

## Parse Warnings
- None

## Input Metadata
- CRM file: crm-demo.csv
- GA4 file: ga4-demo.csv

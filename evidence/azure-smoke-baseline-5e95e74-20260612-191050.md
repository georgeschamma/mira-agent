# Media Plan - MIRA

## Executive Summary
MIRA should run a constrained two-channel demo plan across Paid Search and LinkedIn, preserving coverage while cutting spend to the fixed $1,000 cap. Because both fitted channels are saturated and there is no expansion budget, the strategy is not to scale reach; it is to tighten intent, improve lead quality, and remove inefficient keywords, audiences, and creative paths. Paid Search captures active demand, while LinkedIn qualifies and retargets the most relevant B2B marketing buyers.

## Budget Deployment
| Bucket | Amount | Notes |
|---|---:|---|
| Fitted channels (GA4-backed) | 1,000 | GA4-backed deterministic allocation (performance:allocation) |
| **Total** | **1,000** | Matches brief budget |

## Budget Context
- Brief budget: 1,000
- Current GA4 spend: 3,210
- Net budget change required: 2,210 reduction required
- Expansion budget available: 0
- Policy adjustments: Budget cap active (1,000 < 3,210). Trimming lowest mROI channels.
- GA4 channels with performance data: 2 (Paid Search / google/cpc, Paid Social / linkedin/paid)
- Fitted allocation rows: 2 (Paid Search / google/cpc, Paid Social / linkedin/paid)
- Saturated fitted channels: Paid Search / google/cpc, Paid Social / linkedin/paid
- Brief channels without GA4 data: None

## Budget Allocation
| Channel | Current Spend | Recommended Spend | Delta | Zone | Marginal ROI | Confidence |
|---|---:|---:|---:|---|---:|---|
| Paid Search / google/cpc | 1,800 | 561 | -1,239 | saturated | 0.242 | high |
| Paid Social / linkedin/paid | 1,410 | 439 | -971 | saturated | 0.142 | high |

## Recommended Tests
No recommended tests at this time.

## Audience Strategy
Focus the $1,000 plan on B2B marketers most likely to book a demo now: high-intent searchers researching demo, analytics, attribution, campaign performance, and marketing operations solutions, plus LinkedIn audiences built from tight senior marketing, demand generation, growth, revenue operations, and marketing operations filters. Use CRM and account-based audiences where available, but treat company size, industry, lifecycle stage, and region signals as directional because several segments are sparse. Existing customers should be excluded from cold prospecting and kept to retargeting or upsell-only pools.
- **Primary:** Industry: SaaS (7 CRM records, crm:segment:industry:saas)
  - Targeting: Build paid targeting around the 'SaaS' segment and matched CRM audiences.
- **Secondary:** Company Size: 51-200 (5 CRM records, crm:segment:company_size:51-200)
  - Targeting: Use lookalikes and firmographic targeting around 51-200 accounts.
- **Secondary:** Lifecycle Stage: lead (5 CRM records, crm:segment:lifecycle_stage:lead)
  - Targeting: Retarget and seed lookalikes from the lead lifecycle cohort.

## Channel Rationale
Paid Search should act as the demand-capture layer, reduced to the fitted level and concentrated on exact- and phrase-match demo-intent terms. This protects the channel’s role while avoiding broad exploratory spend in a saturated environment. LinkedIn should act as the demand-qualification layer, reduced to the fitted level and shifted away from broad prospecting toward Matched Audiences, website retargeting, CRM/account lists, and narrow firmographic filters. Across both channels, creative should move to BOFU proof points, demo booking, and pain-specific messaging rather than awareness.

## Expansion Opportunities
There is no expansion budget available and no brief channels without GA4 data, so no new channels should be added to the deterministic allocation. Qualitatively, future tests could explore lower-cost retargeting or arbitrage channels only after the capped plan stabilizes and budget becomes available. Until then, expansion should be limited to in-channel improvements: better audience exclusions, demo-page retargeting, account-list refinement, keyword pruning, and BOFU creative iteration.

## Sequencing & Timing
First, implement the fixed reductions and lock spend to the GA4-backed fitted allocation. Second, rebuild Paid Search around exact and phrase demo-intent terms, pausing high-impression, low-conversion queries. Third, rebuild LinkedIn around Matched Audiences, retargeting pools, and tight senior marketing firmographics, excluding existing customers from cold prospecting. Fourth, align both channels to BOFU demo creative and measure booked demos, qualified demo requests, and downstream MQL-to-SAL quality. Fifth, revisit expansion only after conversion quality and spend efficiency stabilize under the cap.

## Risks & Assumptions
The main risk is learning instability: a $1,000 cap may be too low to produce consistent demo-volume signals across two saturated B2B channels. Paid Search can burn budget quickly if competitive or broad terms remain active. LinkedIn can underdeliver if broad job-title or interest targeting is used instead of account, CRM, and retargeting pools. Sparse CRM segments also create overfitting risk, so audience decisions should not lean too heavily on company size, industry, region, or lifecycle-stage cuts until more conversion volume accumulates.

## Sources & Audit
- MIRA is targeting B2B marketers with a demo-booking goal across LinkedIn and paid search. (brief:raw)
- The plan is capped at a $1,000 budget, requiring a reduction from current GA4 spend. (brief:budget)
- Paid Search / google/cpc has current GA4 cost of $1,800 and response of 6,030. (ga4:channel:paid-search---google-cpc)
- Paid Social / linkedin/paid has current GA4 cost of $1,410 and response of 3,464. (ga4:channel:paid-social---linkedin-paid)
- The fitted allocation places GA4-backed spend at $1,000 across the fitted channels. (performance:allocation)
- LinkedIn Matched Audiences can target website visitors, CRM contacts, or ABM lists for more relevant B2B campaigns. (https://gotoclient.com/en/blog/how-to-master-linkedin-ads-for-b2b-targeting-formats-and-roi-hacks/)
- A B2B SaaS case study used LinkedIn and Google Search to generate qualified demo requests, with LinkedIn Matched Audiences producing lower CPL than other LinkedIn campaigns. (https://ppcgrowthstudio.com/ignites-b2b-saas-roi-98-accurate-ga4-tracking/)
- A B2B campaign paused Google keywords with high impressions but low conversion rates and reallocated toward terms converting below a CPL threshold. (https://paidmediastudio.com/ignite-growth-3-51-roas-from-data-driven-b2b/)

## Parse Warnings
- None

## Input Metadata
- CRM file: crm-demo.csv
- GA4 file: ga4-demo.csv

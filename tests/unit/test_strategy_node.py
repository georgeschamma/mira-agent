from typing import Any

import pytest
from pydantic import ValidationError
from pydantic_ai.models.test import TestModel

from mira_agent.config import Settings
from mira_agent.graph.context import MiraContext
from mira_agent.graph.nodes.strategy import (
    StrategyNarrativeOutput,
    _strategy_prompt,
    render_budget_table,
    render_media_plan_document,
    strategy_node,
    validate_source_claims,
)
from mira_agent.graph.state import ParsedMediaBrief, ResearchFinding
from mira_agent.integrations.crm import AudienceSegment
from mira_agent.integrations.ga4 import ChannelPerformanceSummary
from mira_agent.schemas.auth import CurrentUser
from mira_agent.schemas.media_plan import MediaPlanGraphRequest, SourceClaim
from mira_agent.services.mmm import ChannelAllocation


class FakeRlsClient:
    def __init__(self) -> None:
        self.inserts: list[tuple[str, dict[str, Any]]] = []
        self.updates: list[tuple[str, dict[str, Any], dict[str, str]]] = []

    async def insert(self, table: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
        self.inserts.append((table, payload))
        return [payload]

    async def update(
        self,
        table: str,
        payload: dict[str, Any],
        *,
        filters: dict[str, str],
    ) -> list[dict[str, Any]]:
        self.updates.append((table, payload, filters))
        return [payload | filters]


class UnusedResearchClient:
    async def search(self, query: str, *, num_results: int):
        return []


@pytest.mark.asyncio
async def test_strategy_node_renders_fixed_budget_table_and_saves_document() -> None:
    client = FakeRlsClient()
    model = TestModel(
        custom_output_args={
            "executive_summary": "Increase paid social based on fixed performance math.",
            "audience_strategy": "Use the lead segment.",
            "channel_rationale": "Paid social has the strongest marginal ROI.",
            "expansion_opportunities": "No extra channel tests are needed.",
            "sequencing": "Launch paid social first.",
            "risks": "Sparse channels need review.",
            "claims": [
                {
                    "claim": "Allocation is deterministic.",
                    "source": "performance:allocation",
                },
                {
                    "claim": "Lead segment informs targeting.",
                    "source": "crm:segment:lifecycle_stage:lead",
                },
            ],
        }
    )
    context = MiraContext(
        client=client,  # type: ignore[arg-type]
        user=CurrentUser(id="user_1", token="jwt"),
        settings=Settings(llm_model="test-model", llm_api_key="test", exa_api_key="test"),
        research_client=UnusedResearchClient(),
        model=model,
    )
    state = {
        "campaign_id": "campaign_1",
        "run_id": "run_1",
        "started_at": 0.0,
        "parsed_brief": ParsedMediaBrief(
            org_id="org_1",
            product="MIRA",
            audience="B2B marketers",
            channels=["linkedin"],
            budget=600,
            goal="book demos",
            raw_brief="Product: MIRA",
        ),
        "media_input": {
            "org_id": "org_1",
            "brief": "Product: MIRA",
            "crm_csv_text": "",
            "crm_filename": "crm.csv",
            "ga4_csv_text": "",
            "ga4_filename": "ga4.csv",
        },
        "findings": [
            ResearchFinding(
                title="B2B benchmark",
                url="https://example.com/b2b",
                highlights=["LinkedIn can support B2B demand."],
            )
        ],
        "audience_segments": [
            AudienceSegment(
                reference="crm:segment:lifecycle_stage:lead",
                label="Lifecycle Stage: lead",
                count=2,
                dimension="lifecycle_stage",
                value="lead",
            )
        ],
        "channel_summaries": [
            ChannelPerformanceSummary(
                channel="Paid Social | linkedin/paid",
                row_count=8,
                total_cost=600,
                total_response=1200,
                unique_spend_points=8,
                sufficient_data=True,
                source_ref="ga4:channel:paid-social-linkedin-paid",
            )
        ],
        "allocations": [
            ChannelAllocation(
                channel="Paid Social | linkedin/paid",
                current_spend=300,
                recommended_spend=450,
                delta=150,
                projected_response=900,
                marginal_roi=2.0,
                zone="optimal",
            )
        ],
        "warnings": [],
        "errors": [],
        "crm_warnings": [],
        "ga4_warnings": [],
        "crm_row_count": 2,
        "ga4_row_count": 8,
    }

    result = await strategy_node(state, context)  # type: ignore[arg-type]

    assert "| Paid Social / linkedin/paid | 300 | 450 | 150 | optimal | 2.000 |" in result[
        "document_markdown"
    ]
    assert "## Budget Context" in result["document_markdown"]
    assert "- Brief budget: 600" in result["document_markdown"]
    assert "- Current GA4 spend: 600" in result["document_markdown"]
    sheet_rows = [payload for table, payload in client.inserts if table == "action_sheets"]
    assert sheet_rows[0]["document_markdown"] == result["document_markdown"]
    assert sheet_rows[0]["recommendations"] == []
    audit_nodes = [payload["node"] for table, payload in client.inserts if table == "audit_log"]
    assert "strategy" in audit_nodes
    run_statuses = [
        payload["status"] for table, payload, _filters in client.updates if table == "campaign_runs"
    ]
    assert run_statuses[-1] == "done"


def test_validate_source_claims_rejects_plain_http_sources() -> None:
    with pytest.raises(ValueError, match="Unsupported strategy source"):
        validate_source_claims([SourceClaim(claim="Insecure external source.", source="http://x.test")])


def test_strategy_narrative_requires_source_claims() -> None:
    with pytest.raises(ValidationError):
        StrategyNarrativeOutput(
            executive_summary="Summary",
            audience_strategy="Audience",
            channel_rationale="Channels",
            expansion_opportunities="Expansion",
            sequencing="Sequence",
            risks="Risks",
            claims=[],
        )


@pytest.mark.asyncio
async def test_strategy_fallback_is_marked_partial_and_not_model_backed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = FakeRlsClient()
    context = MiraContext(
        client=client,  # type: ignore[arg-type]
        user=CurrentUser(id="user_1", token="jwt"),
        settings=Settings(llm_model="test-model", llm_api_key="test", exa_api_key="test"),
        research_client=UnusedResearchClient(),
        model=TestModel(),
    )
    state = {
        "campaign_id": "campaign_1",
        "run_id": "run_1",
        "started_at": 0.0,
        "parsed_brief": ParsedMediaBrief(
            org_id="org_1",
            product="MIRA",
            audience="B2B marketers",
            channels=["linkedin"],
            budget=600,
            goal="book demos",
            raw_brief="Product: MIRA",
        ),
        "media_input": {
            "org_id": "org_1",
            "brief": "Product: MIRA",
            "crm_csv_text": "",
            "crm_filename": "crm.csv",
            "ga4_csv_text": "",
            "ga4_filename": "ga4.csv",
        },
        "findings": [],
        "audience_segments": [],
        "channel_summaries": [],
        "allocations": [],
        "warnings": [],
        "errors": [],
        "crm_warnings": [],
        "ga4_warnings": [],
        "crm_row_count": 0,
        "ga4_row_count": 0,
    }

    async def fail_model_run(*args, **kwargs):
        raise RuntimeError("forced model failure")

    monkeypatch.setattr("mira_agent.graph.nodes.strategy.Agent.run", fail_model_run)

    await strategy_node(state, context)  # type: ignore[arg-type]

    audit = [payload for table, payload in client.inserts if table == "audit_log"][-1]
    sheet = [payload for table, payload in client.inserts if table == "action_sheets"][-1]
    run_status = [
        payload["status"] for table, payload, _filters in client.updates if table == "campaign_runs"
    ][-1]
    assert audit["confidence"] == "low"
    assert audit["model_used"] == "deterministic-fallback"
    assert sheet["model_used"] == "deterministic-fallback"
    assert run_status == "partial"


def test_strategy_document_explains_constrained_budget_and_missing_ga4_channels() -> None:
    state = {
        "parsed_brief": ParsedMediaBrief(
            org_id="org_1",
            product="Clorox",
            audience="B2B buyers",
            channels=["Google", "LinkedIn", "Meta", "TikTok"],
            budget=1000,
            goal="increase qualified pipeline",
            raw_brief="Product: Clorox\nBudget: 1000\nChannels: Google, LinkedIn, Meta, TikTok",
        ),
        "findings": [
            ResearchFinding(
                title="Benchmark",
                url="https://example.com/benchmark",
                highlights=["Retargeting tests can support saturated search channels."],
            )
        ],
        "audience_segments": [],
        "channel_summaries": [
            ChannelPerformanceSummary(
                channel="Paid Search | google/cpc",
                row_count=8,
                total_cost=1100,
                total_response=2200,
                unique_spend_points=8,
                sufficient_data=True,
                source_ref="ga4:channel:paid-search-google-cpc",
            ),
            ChannelPerformanceSummary(
                channel="Paid Social | linkedin/paid",
                row_count=8,
                total_cost=880,
                total_response=1800,
                unique_spend_points=8,
                sufficient_data=True,
                source_ref="ga4:channel:paid-social-linkedin-paid",
            ),
        ],
        "allocations": [
            ChannelAllocation(
                channel="Paid Search | google/cpc",
                current_spend=1100,
                recommended_spend=560,
                delta=-540,
                projected_response=1400,
                marginal_roi=1.1,
                zone="saturated",
            ),
            ChannelAllocation(
                channel="Paid Social | linkedin/paid",
                current_spend=880,
                recommended_spend=440,
                delta=-440,
                projected_response=1200,
                marginal_roi=1.4,
                zone="saturated",
            ),
        ],
        "warnings": [
            "20 of the requested budget was left unallocated because fitted channels reached "
            "supported spend caps.",
            "Invalid date 'x'; expected YYYY-MM-DD.",
        ],
    }
    narrative = StrategyNarrativeOutput(
        executive_summary="Use the constrained budget as the baseline.",
        audience_strategy="Use aggregate segments.",
        channel_rationale="Both fitted channels are saturated at the constrained budget.",
        expansion_opportunities=(
            "Meta and TikTok are narrative-only expansion candidates because they lack GA4 "
            "spend history."
        ),
        sequencing="Cut saturated channels first, then test expansion candidates.",
        risks="Expansion candidates need measured spend history before deterministic allocation.",
        claims=[
            SourceClaim(
                claim="Budget allocation is deterministic.",
                source="performance:allocation",
            )
        ],
    )

    document = render_media_plan_document(
        state=state,  # type: ignore[arg-type]
        request=_media_request(),
        table=render_budget_table(state["allocations"]),
        narrative=narrative,
    )
    prompt = _strategy_prompt(state=state, budget_table=render_budget_table(state["allocations"]))

    assert "- Brief budget: 1,000" in document
    assert "- Current GA4 spend: 1,980" in document
    assert "- Net budget change required: 980 reduction required" in document
    assert "- Brief channels without GA4 data: Meta, TikTok" in document
    assert "- Budget warnings: 20 of the requested budget was left unallocated" in document
    assert "Invalid date 'x'; expected YYYY-MM-DD." in document
    assert "Meta and TikTok are narrative-only expansion candidates" in document
    assert "| Meta |" not in document
    assert "Retargeting tests can support saturated search channels." in prompt
    assert "Expansion candidates outside the deterministic table:\nMeta, TikTok" in prompt


def _media_request() -> MediaPlanGraphRequest:
    return MediaPlanGraphRequest(
        org_id="org_1",
        brief="Product: Clorox",
        crm_csv_text="",
        crm_filename="crm.csv",
        ga4_csv_text="",
        ga4_filename="ga4.csv",
    )

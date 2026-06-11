from typing import Any

import pytest
from pydantic_ai.models.test import TestModel

from mira_agent.config import Settings
from mira_agent.graph.context import MiraContext
from mira_agent.graph.nodes.synthesis import synthesize_node
from mira_agent.graph.state import ParsedMediaBrief, ResearchFinding
from mira_agent.integrations.crm import AudienceSegment
from mira_agent.integrations.ga4 import ChannelPerformanceSummary
from mira_agent.schemas.auth import CurrentUser
from mira_agent.services.mmm import ChannelAllocation


class FakeRlsClient:
    def __init__(self) -> None:
        self.inserts: list[tuple[str, dict[str, Any]]] = []

    async def insert(self, table: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
        self.inserts.append((table, payload))
        return [payload]


class UnusedResearchClient:
    async def search(self, query: str, *, num_results: int):
        return []


@pytest.mark.asyncio
async def test_synthesize_node_builds_strategic_brief_and_audit_row() -> None:
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
        "parsed_brief": ParsedMediaBrief(
            org_id="org_1",
            product="Clorox",
            audience="B2B buyers",
            channels=["Google", "LinkedIn", "Meta", "TikTok"],
            budget=1000,
            goal="increase qualified pipeline",
            raw_brief="Product: Clorox",
        ),
        "findings": [
            ResearchFinding(
                title="Benchmark",
                url="https://example.com/benchmark",
                highlights=["Retargeting can complement saturated search demand."],
            )
        ],
        "audience_segments": [
            AudienceSegment(
                reference="crm:segment:lifecycle_stage:lead",
                label="Lifecycle Stage: lead",
                count=5,
                dimension="lifecycle_stage",
                value="lead",
            )
        ],
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
        "warnings": [],
        "errors": [],
    }

    result = await synthesize_node(state, context)  # type: ignore[arg-type]

    strategic_brief = result["strategic_brief"]
    assert "Brief budget is 1,000 versus current GA4 spend of 1,980" in (
        strategic_brief.situation_summary
    )
    assert "Paid Search / google/cpc" in strategic_brief.saturation_diagnosis
    assert any("Meta" in item for item in strategic_brief.expansion_opportunities)
    assert any("Paid Search / google/cpc" in item for item in strategic_brief.channel_moves)
    assert any(claim.source == "brief:channels" for claim in strategic_brief.source_claims)

    audit = [payload for table, payload in client.inserts if table == "audit_log"][-1]
    assert audit["node"] == "synthesize"
    assert audit["step_index"] == 4
    assert audit["model_used"] == "none"

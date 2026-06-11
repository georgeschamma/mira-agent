from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest
from pydantic_ai import Agent
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
async def test_synthesis_agent_structured_output() -> None:
    client = FakeRlsClient()
    # PydanticAI model mock
    model = TestModel(
        custom_output_args={
            "planning_mode": "growth",
            "situation_summary": "Situation summary from LLM.",
            "saturation_diagnosis": "Saturated Google.",
            "channel_roles": {"Paid Search | google/cpc": "harvest"},
            "audience_priorities": ["lead segment"],
            "channel_moves": ["google scale up"],
            "do_not_scale": ["linkedin"],
            "expansion_tests": [
                {
                    "channel": "Paid Social | tiktok/paid",
                    "monthly_budget_range": "$1,000–$2,000",
                    "hypothesis": "Test TikTok",
                    "primary_kpi": "CPA",
                    "audience_fit": "Gen Z",
                    "source": "brief:channels",
                }
            ],
            "budget_waterfall": ["Water-fill harvest"],
            "key_risks": ["Low data"],
            "research_insights": ["benchmarks"],
            "source_claims": [{"claim": "benchmarks", "source": "https://example.com"}],
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
        "parsed_brief": ParsedMediaBrief(
            org_id="org_1",
            product="MIRA",
            audience="B2B buyers",
            channels=["google", "tiktok"],
            budget=5000,
            goal="grow pipeline",  # grow -> growth mode
            raw_brief="Product: MIRA",
        ),
        "findings": [],
        "audience_segments": [],
        "channel_summaries": [],
        "allocations": [],
        "warnings": [],
        "errors": [],
    }

    result = await synthesize_node(state, context)  # type: ignore[arg-type]
    strategic_brief = result["strategic_brief"]
    
    assert strategic_brief.planning_mode == "growth"
    assert strategic_brief.situation_summary == "Situation summary from LLM."
    assert strategic_brief.expansion_tests[0].channel == "Paid Social | tiktok/paid"


@pytest.mark.asyncio
async def test_synthesis_fallback_on_llm_failure() -> None:
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
            channels=["Google", "LinkedIn", "Meta"],
            budget=1000,
            goal="reduce CAC",  # reduce CAC -> efficiency mode
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
            )
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
            )
        ],
        "warnings": [],
        "errors": [],
        "expansion_budget": 440,
        "expansion_candidates": ["LinkedIn", "Meta"],
    }

    # Force agent.run to fail to trigger fallback path
    with patch.object(Agent, "run", side_effect=RuntimeError("LLM is down")):
        result = await synthesize_node(state, context)  # type: ignore[arg-type]
    
    strategic_brief = result["strategic_brief"]
    
    assert strategic_brief.planning_mode == "efficiency"
    assert (
        "Brief budget is 1,000 versus current GA4 spend of 1,100"
        in strategic_brief.situation_summary
    )
    assert len(strategic_brief.expansion_tests) == 2
    assert any(err.code == "LLM_SYNTHESIS_FAILED" for err in state["errors"])


@pytest.mark.asyncio
async def test_expansion_tests_generated_when_unallocated_budget() -> None:
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
            channels=["Google", "LinkedIn", "Meta"],
            budget=2000,
            goal="grow pipeline",
            raw_brief="Product: Clorox",
        ),
        "findings": [],
        "audience_segments": [],
        "channel_summaries": [
            ChannelPerformanceSummary(
                channel="Paid Search | google/cpc",
                row_count=8,
                total_cost=1000,
                total_response=2000,
                unique_spend_points=8,
                sufficient_data=True,
                source_ref="ga4:channel:paid-search-google-cpc",
            )
        ],
        "allocations": [
            ChannelAllocation(
                channel="Paid Search | google/cpc",
                current_spend=1000,
                recommended_spend=1000,
                delta=0,
                projected_response=1400,
                marginal_roi=0.01,
                zone="saturated",
            )
        ],
        "warnings": [],
        "errors": [],
        "expansion_budget": 1000,
        "expansion_candidates": ["LinkedIn", "Meta"],
    }

    # Force agent.run to fail to trigger fallback path,
    # which generates the expansion tests deterministically
    with patch.object(Agent, "run", side_effect=RuntimeError("Validation Error")):
        result = await synthesize_node(state, context)  # type: ignore[arg-type]
    
    strategic_brief = result["strategic_brief"]
    
    assert len(strategic_brief.expansion_tests) == 2
    assert strategic_brief.expansion_tests[0].channel == "LinkedIn"
    assert strategic_brief.expansion_tests[1].channel == "Meta"

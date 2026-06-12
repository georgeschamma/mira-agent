from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic_ai.models.test import TestModel

from mira_agent.config import Settings
from mira_agent.graph.context import MiraContext
from mira_agent.graph.nodes.performance import performance_node
from mira_agent.graph.nodes.synthesis import synthesize_node
from mira_agent.graph.state import ParsedMediaBrief, ResearchInsights
from mira_agent.integrations.crm import AudienceSegment
from mira_agent.schemas.auth import CurrentUser


class FakeRlsClient:
    async def insert(self, table: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
        return [payload]


class UnusedResearchClient:
    async def search(self, query: str, *, num_results: int):
        return []


@pytest.mark.asyncio
async def test_10k_growth_demo_matches_golden_waterfall() -> None:
    sample_path = Path("samples/ga4-demo.csv")
    expected_path = Path("tests/fixtures/expected/10k-growth-waterfall.json")
    expected = json.loads(expected_path.read_text())

    state = {
        "campaign_id": "campaign_1",
        "run_id": "run_1",
        "parsed_brief": ParsedMediaBrief(
            org_id="org_1",
            product="MIRA",
            audience="B2B marketers",
            channels=["google", "linkedin", "meta", "tiktok"],
            budget=10000,
            goal="grow pipeline",
            raw_brief="Product: MIRA",
        ),
        "media_input": {
            "org_id": "org_1",
            "brief": "Product: MIRA",
            "crm_csv_text": "",
            "crm_filename": "crm.csv",
            "ga4_csv_text": sample_path.read_text(),
            "ga4_filename": "ga4.csv",
        },
        "findings": [],
        "audience_segments": [
            AudienceSegment(
                reference="crm:segment:company_size:51-200",
                label="Company Size: 51-200",
                count=7,
                dimension="company_size",
                value="51-200",
            )
        ],
        "research_insights_data": ResearchInsights(),
    }
    model = TestModel(
        custom_output_args={
            "planning_mode": "growth",
            "situation_summary": "Growth plan.",
            "saturation_diagnosis": "Search and LinkedIn are saturated.",
            "channel_roles": {},
            "audience_priorities": [],
            "channel_moves": [],
            "do_not_scale": [],
            "expansion_tests": [],
            "budget_waterfall": [],
            "key_risks": [],
            "research_insights": [],
            "source_claims": [],
            "expansion_opportunities": [],
        }
    )
    context = MiraContext(
        client=FakeRlsClient(),  # type: ignore[arg-type]
        user=CurrentUser(id="user_1", token="jwt"),
        settings=Settings(llm_model="test-model", llm_api_key="test", exa_api_key="test"),
        research_client=UnusedResearchClient(),
        model=model,
    )

    perf = await performance_node(state, context)  # type: ignore[arg-type]
    state.update(perf)
    syn = await synthesize_node(state, context)  # type: ignore[arg-type]
    brief = syn["strategic_brief"]

    observed = {
        "allocations": [
            {
                "channel": item.channel,
                "recommended_spend": item.recommended_spend,
                "zone": item.zone,
                "confidence": item.confidence,
            }
            for item in perf["allocations"]
        ],
        "expansion_budget": perf["expansion_budget"],
        "expansion_candidates": perf["expansion_candidates"],
        "expansion_allocations": [
            {
                "channel": item.channel,
                "phase1_test_budget": item.phase1_test_budget,
                "staged_reserve": item.staged_reserve,
            }
            for item in syn["expansion_allocations"]
        ],
        "expansion_reserve_pool": syn["expansion_reserve_pool"],
        "budget_waterfall": brief.budget_waterfall,
    }

    assert observed == expected

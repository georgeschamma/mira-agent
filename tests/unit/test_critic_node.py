from __future__ import annotations

import pytest

from mira_agent.config import Settings
from mira_agent.graph.context import MiraContext
from mira_agent.graph.nodes.critic import critic_node
from mira_agent.graph.state import (
    MiraMediaPlanState,
    ParsedMediaBrief,
    StrategicBrief,
)
from mira_agent.schemas.auth import CurrentUser
from mira_agent.services.allocation_policy import ExpansionAllocation
from mira_agent.services.mmm import ChannelAllocation


class FakeRlsClient:
    def __init__(self) -> None:
        self.inserts: list[tuple[str, dict[str, any]]] = []
        self.updates: list[tuple[str, dict[str, any], dict[str, str]]] = []

    async def insert(self, table: str, payload: dict[str, any]) -> list[dict[str, any]]:
        self.inserts.append((table, payload))
        return [payload]

    async def update(
        self,
        table: str,
        payload: dict[str, any],
        *,
        filters: dict[str, str],
    ) -> list[dict[str, any]]:
        self.updates.append((table, payload, filters))
        return [payload | filters]


def _test_context(client: FakeRlsClient) -> MiraContext:
    return MiraContext(
        client=client,  # type: ignore[arg-type]
        user=CurrentUser(id="user_1", token="jwt"),
        settings=Settings(llm_model="test-model", llm_api_key="test", exa_api_key="test"),
        research_client=None,  # type: ignore[arg-type]
        model=None,  # type: ignore[arg-type]
    )


def _base_state() -> MiraMediaPlanState:
    return {
        "campaign_id": "campaign_1",
        "run_id": "run_1",
        "started_at": 0.0,
        "parsed_brief": ParsedMediaBrief(
            org_id="org_1",
            product="Test Product",
            audience="B2B",
            channels=["google", "linkedin"],
            budget=1000,
            goal="grow",
            raw_brief="brief",
        ),
        "media_input": {
            "org_id": "org_1",
            "brief": "brief",
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
        "document_metadata": {
            "source_claims": [{"claim": "Valid GA4 data.", "source": "ga4:google"}]
        },
        "strategy_retries": 0,
    }


@pytest.mark.asyncio
async def test_critic_passes_valid_state() -> None:
    client = FakeRlsClient()
    context = _test_context(client)
    state = _base_state()

    # Create valid strategic brief
    state["strategic_brief"] = StrategicBrief(
        planning_mode="growth",
        situation_summary="Situation summary",
        saturation_diagnosis="No saturated channels scaled.",
        do_not_scale=[],
        expansion_tests=[],
    )

    result = await critic_node(state, context)

    assert not result.get("critic_failed")
    assert result.get("strategy_remediation") == ""


@pytest.mark.asyncio
async def test_critic_fails_do_not_scale_violation() -> None:
    client = FakeRlsClient()
    context = _test_context(client)
    state = _base_state()

    # Scale up search which is in do_not_scale list
    state["strategic_brief"] = StrategicBrief(
        planning_mode="growth",
        situation_summary="Situation summary",
        saturation_diagnosis="Google is saturated.",
        do_not_scale=["Paid Search | google/cpc"],
        expansion_tests=[],
    )
    state["allocations"] = [
        ChannelAllocation(
            channel="Paid Search | google/cpc",
            current_spend=100,
            recommended_spend=200,
            delta=100,  # Delta > 0.5
            projected_response=150,
            marginal_roi=0.01,
            zone="saturated",
        )
    ]

    result = await critic_node(state, context)

    assert result.get("critic_failed") is True
    assert "Contradiction" in result.get("strategy_remediation", "")
    assert "DO NOT SCALE" in result.get("strategy_remediation", "")


@pytest.mark.asyncio
async def test_critic_do_not_scale_requires_exact_channel_name() -> None:
    client = FakeRlsClient()
    context = _test_context(client)
    state = _base_state()

    state["strategic_brief"] = StrategicBrief(
        planning_mode="growth",
        situation_summary="Situation summary",
        saturation_diagnosis="Google is saturated.",
        do_not_scale=["Paid Search / google/cpc"],
        expansion_tests=[],
    )
    state["allocations"] = [
        ChannelAllocation(
            channel="Paid Search | google/cpc",
            current_spend=100,
            recommended_spend=200,
            delta=100,
            projected_response=150,
            marginal_roi=0.01,
            zone="saturated",
        )
    ]

    result = await critic_node(state, context)

    assert not result.get("critic_failed")


@pytest.mark.asyncio
async def test_critic_fails_missing_expansion_tests() -> None:
    client = FakeRlsClient()
    context = _test_context(client)
    state = _base_state()

    state["expansion_budget"] = 500.0
    state["expansion_allocations"] = [
        ExpansionAllocation(
            channel="meta",
            phase1_test_budget=100,
            staged_reserve=325,
            weight_notes="Expansion allocation for meta.",
        )
    ]
    state["strategic_brief"] = StrategicBrief(
        planning_mode="growth",
        situation_summary="Situation summary",
        saturation_diagnosis="Diagnosis",
        do_not_scale=[],
        expansion_tests=[],  # Empty tests list!
    )

    result = await critic_node(state, context)

    assert result.get("critic_failed") is True
    assert "no expansion tests were defined" in result.get("strategy_remediation", "")


@pytest.mark.asyncio
async def test_critic_allows_reserve_only_expansion_budget() -> None:
    client = FakeRlsClient()
    context = _test_context(client)
    state = _base_state()

    state["expansion_budget"] = 500.0
    state["expansion_reserve_pool"] = 500.0
    state["expansion_allocations"] = []
    state["strategic_brief"] = StrategicBrief(
        planning_mode="growth",
        situation_summary="Situation summary",
        saturation_diagnosis="Diagnosis",
        do_not_scale=[],
        expansion_tests=[],
    )

    result = await critic_node(state, context)

    assert not result.get("critic_failed")


@pytest.mark.asyncio
async def test_critic_fails_invalid_claim_source() -> None:
    client = FakeRlsClient()
    context = _test_context(client)
    state = _base_state()

    state["document_metadata"] = {
        "source_claims": [{"claim": "Invalid source format.", "source": "invalid:source"}]
    }
    state["strategic_brief"] = StrategicBrief(
        planning_mode="growth",
        situation_summary="Situation summary",
        saturation_diagnosis="Diagnosis",
        do_not_scale=[],
        expansion_tests=[],
    )

    result = await critic_node(state, context)

    assert result.get("critic_failed") is True
    assert "Claim validation failure" in result.get("strategy_remediation", "")


@pytest.mark.asyncio
async def test_critic_fails_efficiency_positive_delta() -> None:
    client = FakeRlsClient()
    context = _test_context(client)
    state = _base_state()

    state["strategic_brief"] = StrategicBrief(
        planning_mode="efficiency",
        situation_summary="Situation summary",
        saturation_diagnosis="Diagnosis",
        do_not_scale=[],
        expansion_tests=[],
    )
    state["allocations"] = [
        ChannelAllocation(
            channel="Paid Search | google/cpc",
            current_spend=100,
            recommended_spend=200,
            delta=100,  # Delta is positive
            projected_response=150,
            marginal_roi=1.5,
            zone="optimal",
        )
    ]

    result = await critic_node(state, context)

    assert result.get("critic_failed") is True
    assert "efficiency" in result.get("strategy_remediation", "")

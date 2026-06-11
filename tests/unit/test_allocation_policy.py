from __future__ import annotations

from mira_agent.graph.state import ParsedMediaBrief
from mira_agent.integrations.ga4 import ChannelPerformanceSummary
from mira_agent.services.allocation_policy import (
    apply_allocation_policy,
    split_expansion_budget,
)
from mira_agent.services.mmm import (
    AllocationPlan,
    ChannelAllocation,
    ChannelCurve,
)


def _hill_curve(channel: str, vmax: float, k: float, a: float) -> ChannelCurve:
    return ChannelCurve(
        channel=channel,
        model="hill",
        params={"vmax": vmax, "k": k, "a": a},
        r_squared=1.0,
        n_points=20,
        confidence="high",
    )


def test_saturated_channels_no_increase() -> None:
    # Scenario S2: budget 10000, spend 1980, 2 saturated channels
    # Curves modeled so they have low marginal ROI (< 0.05) at current spend
    curves = [
        _hill_curve("Paid Search | google/cpc", 1200, 10, 1.0),
        _hill_curve("Paid Social | linkedin/paid", 900, 10, 1.0),
    ]
    raw_allocations = [
        ChannelAllocation(
            channel="Paid Search | google/cpc",
            current_spend=1100,
            recommended_spend=2200,  # Scaled up raw
            delta=1100,
            projected_response=1190,
            marginal_roi=0.002,  # Saturated + weak mROI (< 0.05)
            zone="saturated",
        ),
        ChannelAllocation(
            channel="Paid Social | linkedin/paid",
            current_spend=880,
            recommended_spend=1760,  # Scaled up raw
            delta=880,
            projected_response=890,
            marginal_roi=0.003,  # Saturated + weak mROI (< 0.05)
            zone="saturated",
        ),
    ]
    raw_plan = AllocationPlan(
        allocations=raw_allocations,
        total_budget=10000,
        baseline_total_response=2000,
        projected_total_response=2080,
    )
    brief = ParsedMediaBrief(
        org_id="org_1",
        product="MIRA",
        audience="B2B",
        channels=["google", "linkedin", "meta", "tiktok"],
        budget=10000,
        goal="grow",
        raw_brief="",
    )
    summaries = [
        ChannelPerformanceSummary(
            channel="Paid Search | google/cpc",
            row_count=8,
            total_cost=1100,
            total_response=1100,
            unique_spend_points=8,
            sufficient_data=True,
            source_ref="ga4:google",
        ),
        ChannelPerformanceSummary(
            channel="Paid Social | linkedin/paid",
            row_count=8,
            total_cost=880,
            total_response=880,
            unique_spend_points=8,
            sufficient_data=True,
            source_ref="ga4:linkedin",
        ),
    ]

    policy_plan = apply_allocation_policy(
        raw_plan=raw_plan,
        insufficient=[],
        brief=brief,
        summaries=summaries,
        brief_channels=brief.channels,
        curves=curves,
    )

    # Verify both got capped at current spend
    allocs = {a.channel: a for a in policy_plan.fitted_allocations}
    assert allocs["Paid Search | google/cpc"].recommended_spend == 1100
    assert allocs["Paid Social | linkedin/paid"].recommended_spend == 880
    # expansion_budget should be approximately 10000 - 1980 = 8020
    assert abs(policy_plan.expansion_budget - 8020) < 1e-3
    assert set(policy_plan.expansion_candidates) == {"meta", "tiktok"}


def test_budget_cap_mode_trim_lowest_mroi() -> None:
    # Scenario S1: budget 1000, spend 1980 (1100 + 880), trim lowest mROI
    curves = [
        _hill_curve("Paid Search | google/cpc", 2000, 500, 1.0),
        _hill_curve("Paid Social | linkedin/paid", 2000, 500, 1.0),
    ]
    # Google has lower mROI (closer to saturation or lower ceiling)
    raw_allocations = [
        ChannelAllocation(
            channel="Paid Search | google/cpc",
            current_spend=1100,
            recommended_spend=1100,
            delta=0,
            projected_response=1000,
            marginal_roi=0.1,  # Lower mROI
            zone="saturated",
        ),
        ChannelAllocation(
            channel="Paid Social | linkedin/paid",
            current_spend=880,
            recommended_spend=880,
            delta=0,
            projected_response=1000,
            marginal_roi=0.2,  # Higher mROI
            zone="saturated",
        ),
    ]
    raw_plan = AllocationPlan(
        allocations=raw_allocations,
        total_budget=1000,
        baseline_total_response=2000,
        projected_total_response=2000,
    )
    brief = ParsedMediaBrief(
        org_id="org_1",
        product="MIRA",
        audience="B2B",
        channels=["google", "linkedin"],
        budget=1000,
        goal="efficiency",
        raw_brief="",
    )
    summaries = [
        ChannelPerformanceSummary(
            channel="Paid Search | google/cpc",
            row_count=8,
            total_cost=1100,
            total_response=1100,
            unique_spend_points=8,
            sufficient_data=True,
            source_ref="ga4:google",
        ),
        ChannelPerformanceSummary(
            channel="Paid Social | linkedin/paid",
            row_count=8,
            total_cost=880,
            total_response=880,
            unique_spend_points=8,
            sufficient_data=True,
            source_ref="ga4:linkedin",
        ),
    ]

    policy_plan = apply_allocation_policy(
        raw_plan=raw_plan,
        insufficient=[],
        brief=brief,
        summaries=summaries,
        brief_channels=brief.channels,
        curves=curves,
    )

    # Verify that total sum is trimmed to exactly brief.budget (1000)
    allocs = {a.channel: a for a in policy_plan.fitted_allocations}
    total = sum(a.recommended_spend for a in policy_plan.fitted_allocations)
    assert abs(total - 1000) < 1e-3
    # Saturated/lower mROI Google cpc should have been trimmed more than LinkedIn
    assert allocs["Paid Search | google/cpc"].recommended_spend < 1100
    assert any("Budget cap active" in note for note in policy_plan.policy_notes)


def test_insufficient_data_hold_and_trim() -> None:
    # Case: All channels insufficient_data, Budget 1000, spend 1980 (1100 + 880)
    # Expected: Hold and trim proportionally/equally to 1000
    brief = ParsedMediaBrief(
        org_id="org_1",
        product="MIRA",
        audience="B2B",
        channels=["google", "linkedin"],
        budget=1000,
        goal="efficiency",
        raw_brief="",
    )
    insufficient = [
        ChannelAllocation(
            channel="Paid Search | google/cpc",
            current_spend=1100,
            recommended_spend=1100,
            delta=0,
            projected_response=None,
            marginal_roi=None,
            zone="insufficient_data",
        ),
        ChannelAllocation(
            channel="Paid Social | linkedin/paid",
            current_spend=880,
            recommended_spend=880,
            delta=0,
            projected_response=None,
            marginal_roi=None,
            zone="insufficient_data",
        ),
    ]
    raw_plan = AllocationPlan(
        allocations=[],
        total_budget=1000,
        baseline_total_response=0.0,
        projected_total_response=0.0,
    )
    summaries = [
        ChannelPerformanceSummary(
            channel="Paid Search | google/cpc",
            row_count=4,
            total_cost=1100,
            total_response=0,
            unique_spend_points=4,
            sufficient_data=False,
            source_ref="ga4:google",
        ),
        ChannelPerformanceSummary(
            channel="Paid Social | linkedin/paid",
            row_count=4,
            total_cost=880,
            total_response=0,
            unique_spend_points=4,
            sufficient_data=False,
            source_ref="ga4:linkedin",
        ),
    ]

    policy_plan = apply_allocation_policy(
        raw_plan=raw_plan,
        insufficient=insufficient,
        brief=brief,
        summaries=summaries,
        brief_channels=brief.channels,
        curves=[],
    )

    total = sum(a.recommended_spend for a in policy_plan.fitted_allocations)
    assert abs(total - 1000) < 1e-3


def test_expansion_budget_no_candidates_warning() -> None:
    # Scenario: budget 10000, spend 1980, no missing brief channels
    curves = [
        _hill_curve("Paid Search | google/cpc", 1200, 10, 1.0),
        _hill_curve("Paid Social | linkedin/paid", 900, 10, 1.0),
    ]
    raw_allocations = [
        ChannelAllocation(
            channel="Paid Search | google/cpc",
            current_spend=1100,
            recommended_spend=1100,
            delta=0,
            projected_response=1190,
            marginal_roi=0.002,
            zone="saturated",
        ),
        ChannelAllocation(
            channel="Paid Social | linkedin/paid",
            current_spend=880,
            recommended_spend=880,
            delta=0,
            projected_response=890,
            marginal_roi=0.003,
            zone="saturated",
        ),
    ]
    raw_plan = AllocationPlan(
        allocations=raw_allocations,
        total_budget=10000,
        baseline_total_response=2000,
        projected_total_response=2080,
    )
    brief = ParsedMediaBrief(
        org_id="org_1",
        product="MIRA",
        audience="B2B",
        channels=["google", "linkedin"],
        budget=10000,
        goal="grow",
        raw_brief="",
    )
    summaries = [
        ChannelPerformanceSummary(
            channel="Paid Search | google/cpc",
            row_count=8,
            total_cost=1100,
            total_response=1100,
            unique_spend_points=8,
            sufficient_data=True,
            source_ref="ga4:google",
        ),
        ChannelPerformanceSummary(
            channel="Paid Social | linkedin/paid",
            row_count=8,
            total_cost=880,
            total_response=880,
            unique_spend_points=8,
            sufficient_data=True,
            source_ref="ga4:linkedin",
        ),
    ]

    policy_plan = apply_allocation_policy(
        raw_plan=raw_plan,
        insufficient=[],
        brief=brief,
        summaries=summaries,
        brief_channels=brief.channels,
        curves=curves,
    )

    assert policy_plan.expansion_budget == 8020
    assert not policy_plan.expansion_candidates
    assert any("has no candidate channels from brief" in note for note in policy_plan.policy_notes)


def test_split_expansion_budget_weights_holdback_ramp_cap_rounding_and_sum() -> None:
    allocations, reserve_pool = split_expansion_budget(
        expansion_budget=10000,
        candidates=["Meta", "TikTok"],
        audience_hints=["Meta performs well for the audience"],
        suggested_test_channels=["Meta benchmark"],
        max_fitted_spend=1000,
    )

    by_channel = {allocation.channel: allocation for allocation in allocations}

    assert [allocation.channel for allocation in allocations] == ["meta", "tiktok"]
    assert by_channel["meta"].phase1_test_budget == 3000
    assert by_channel["meta"].staged_reserve == 2650
    assert by_channel["tiktok"].phase1_test_budget == 2800
    assert by_channel["tiktok"].staged_reserve == 0
    assert reserve_pool == 1550
    assert "audience hint +0.5" in by_channel["meta"].weight_notes
    assert "research suggestion +0.5" in by_channel["meta"].weight_notes
    total = reserve_pool + sum(
        item.phase1_test_budget + item.staged_reserve for item in allocations
    )
    assert total == 10000


def test_split_expansion_budget_no_candidates_all_reserve() -> None:
    allocations, reserve_pool = split_expansion_budget(
        expansion_budget=5000,
        candidates=[],
        audience_hints=["meta"],
        suggested_test_channels=["tiktok"],
        max_fitted_spend=1000,
    )

    assert allocations == []
    assert reserve_pool == 5000

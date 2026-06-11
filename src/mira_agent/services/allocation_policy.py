from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from mira_agent.services.mmm import (
    ChannelAllocation,
    _zone,
    marginal_roi,
    response_at,
)

if TYPE_CHECKING:
    from mira_agent.graph.state import ParsedMediaBrief
    from mira_agent.integrations.ga4 import ChannelPerformanceSummary
    from mira_agent.services.mmm import AllocationPlan, ChannelCurve

SATURATED_MROI_CEILING = 0.05
UNALLOCATED_THRESHOLD = 0.01


@dataclass
class PolicyAllocationPlan:
    fitted_allocations: list[ChannelAllocation]  # deterministic, post-policy
    expansion_budget: float
    expansion_candidates: list[str]  # brief channels missing GA4
    policy_notes: list[str]  # auditable reasons per channel
    mmm_raw_allocations: list[ChannelAllocation]  # preserved for audit


def apply_allocation_policy(
    raw_plan: AllocationPlan,
    insufficient: list[ChannelAllocation],
    brief: ParsedMediaBrief,
    summaries: list[ChannelPerformanceSummary],
    brief_channels: list[str],
    curves: list[ChannelCurve],
) -> PolicyAllocationPlan:
    # Preserve raw allocations for audit
    mmm_raw_allocations = list(raw_plan.allocations) + list(insufficient)
    curves_map = {c.channel: c for c in curves}

    # Initialize recommends with the raw values
    spends = {}
    for a in raw_plan.allocations:
        spends[a.channel] = a.recommended_spend
    for a in insufficient:
        spends[a.channel] = a.recommended_spend

    policy_notes = []

    # Rule 1 & Rule 4: No scale-up on saturated + weak mROI
    # If all channels are saturated, raw cap ratio is lowered,
    # but here we enforce the policy ceiling.
    for a in raw_plan.allocations:
        if (
            a.zone == "saturated"
            and a.marginal_roi is not None
            and a.marginal_roi < SATURATED_MROI_CEILING
        ):
            if spends[a.channel] > a.current_spend:
                old_val = spends[a.channel]
                spends[a.channel] = a.current_spend
                policy_notes.append(
                    f"Capped saturated channel {a.channel} at current spend "
                    f"{a.current_spend:,.0f} (was {old_val:,.0f}) due to "
                    "low marginal ROI."
                )

    # Rule 2: Budget cap mode (brief budget < current spend)
    current_total_spend = sum(a.current_spend for a in raw_plan.allocations + insufficient)
    is_budget_cap = brief.budget > 0 and brief.budget < current_total_spend

    target_budget = brief.budget if brief.budget > 0 else current_total_spend
    if is_budget_cap:
        policy_notes.append(
            f"Budget cap active ({brief.budget:,.0f} < "
            f"{current_total_spend:,.0f}). Trimming lowest mROI channels."
        )

    # Trim if total spend exceeds the target budget
    total_spend = sum(spends.values())
    if total_spend > target_budget:
        step = 1.0
        while total_spend - target_budget > 1e-3:
            best_channel = None
            lowest_mroi = float("inf")

            for channel, s in spends.items():
                if s <= 0:
                    continue
                # Compute mROI at s
                if channel in curves_map:
                    m = marginal_roi(curves_map[channel], s)
                else:
                    # Insufficient data channels have no curve; treat as neutral low mROI (0.01)
                    m = 0.01

                if m < lowest_mroi:
                    lowest_mroi = m
                    best_channel = channel

            if best_channel is None:
                break

            dec = min(step, total_spend - target_budget, spends[best_channel])
            spends[best_channel] -= dec
            total_spend = sum(spends.values())

    # Rule 3: Growth mode / unallocated budget
    allocated_sum = sum(spends.values())
    unallocated = brief.budget - allocated_sum if brief.budget > 0 else 0.0
    expansion_budget = max(unallocated, 0.0)

    # Find expansion candidates: brief channels missing from GA4
    ga4_channels = [s.channel for s in summaries]
    # Simple token matching / check
    from mira_agent.graph.nodes.strategy import channels_without_ga4_data
    expansion_candidates = channels_without_ga4_data(brief_channels, ga4_channels)

    if expansion_budget > UNALLOCATED_THRESHOLD:
        if expansion_candidates:
            policy_notes.append(
                f"Created expansion budget of {expansion_budget:,.0f} "
                f"for channels: {', '.join(expansion_candidates)}."
            )
        else:
            policy_notes.append(
                f"Unallocated budget of {expansion_budget:,.0f} has no "
                "candidate channels from brief. Suggest expanding brief "
                "channels or designating a reserve test pool."
            )

    # Reconstruct ChannelAllocation list
    fitted_allocations: list[ChannelAllocation] = []
    for a in raw_plan.allocations:
        rec = spends[a.channel]
        curve = curves_map[a.channel]
        fitted_allocations.append(
            ChannelAllocation(
                channel=a.channel,
                current_spend=a.current_spend,
                recommended_spend=rec,
                delta=rec - a.current_spend,
                projected_response=response_at(curve, rec),
                marginal_roi=marginal_roi(curve, rec),
                zone=_zone(curve, rec),
            )
        )
    for a in insufficient:
        rec = spends[a.channel]
        fitted_allocations.append(
            ChannelAllocation(
                channel=a.channel,
                current_spend=a.current_spend,
                recommended_spend=rec,
                delta=rec - a.current_spend,
                projected_response=None,
                marginal_roi=None,
                zone=a.zone,
            )
        )

    return PolicyAllocationPlan(
        fitted_allocations=fitted_allocations,
        expansion_budget=expansion_budget,
        expansion_candidates=expansion_candidates,
        policy_notes=policy_notes,
        mmm_raw_allocations=mmm_raw_allocations,
    )

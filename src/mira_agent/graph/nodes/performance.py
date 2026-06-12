from __future__ import annotations

from mira_agent.graph.context import MiraContext
from mira_agent.graph.state import MiraMediaPlanState, NodeError
from mira_agent.integrations.ga4 import CsvParseError, parse_ga4_csv
from mira_agent.repositories.campaigns import write_audit_row
from mira_agent.schemas.media_plan import MediaPlanGraphRequest
from mira_agent.services.allocation_policy import GROWTH_CAP_RATIO, apply_allocation_policy
from mira_agent.services.mmm import (
    ChannelAllocation,
    _zone,
    fit_channel,
    insufficient_allocation,
    optimize_allocation,
)


async def performance_node(state: MiraMediaPlanState, context: MiraContext) -> MiraMediaPlanState:
    request = MediaPlanGraphRequest.model_validate(state["media_input"])
    campaign_id = state["campaign_id"]
    run_id = state["run_id"]
    parsed_brief = state["parsed_brief"]

    try:
        result = parse_ga4_csv(request.ga4_csv_text)
    except CsvParseError as exc:
        await write_audit_row(
            client=context.client,
            campaign_id=campaign_id,
            run_id=run_id,
            step_index=3,
            node="performance",
            summary="GA4 performance parsing failed.",
            source="ga4:csv",
            confidence="low",
            model_used="none",
        )
        return {
            "channel_summaries": [],
            "allocations": [],
            "warnings": [],
            "ga4_warnings": [],
            "ga4_row_count": 0,
            "errors": [
                NodeError(node="performance", code="GA4_PARSE_FAILED", message=str(exc)),
            ],
        }

    curves = []
    insufficient: list[ChannelAllocation] = []
    for observation in result.observations:
        curve = fit_channel(observation)
        if curve is None:
            insufficient.append(
                insufficient_allocation(
                    observation.channel,
                    result.current_spend.get(observation.channel, 0.0),
                )
            )
            continue
        curves.append(curve)

    total_budget = parsed_brief.budget or sum(result.current_spend.values())
    current_total_spend = sum(result.current_spend.values())
    held_budget = sum(item.recommended_spend for item in insufficient)
    if held_budget > total_budget and held_budget > 0:
        scale = total_budget / held_budget
        insufficient = [
            ChannelAllocation(
                channel=item.channel,
                current_spend=item.current_spend,
                recommended_spend=item.recommended_spend * scale,
                delta=(item.recommended_spend * scale) - item.current_spend,
                projected_response=None,
                marginal_roi=None,
                zone=item.zone,
            )
            for item in insufficient
        ]
        fitted_budget = 0.0
    else:
        fitted_budget = max(total_budget - held_budget, 0.0)

    goal_lower = parsed_brief.goal.lower()
    planning_mode = (
        "efficiency"
        if any(term in goal_lower for term in ("reduce cac", "efficiency", "cut"))
        else "growth"
        if any(term in goal_lower for term in ("grow", "scale", "pipeline"))
        else "balanced"
    )

    # Growth briefs with large budget headroom should allow stronger scale-up before
    # the policy layer trims weak saturated channels back down.
    all_saturated = len(curves) > 0 and all(
        _zone(c, result.current_spend.get(c.channel, 0.0)) == "saturated"
        for c in curves
    )
    if (
        planning_mode == "growth"
        and total_budget > 1.25 * current_total_spend
        and current_total_spend > 0
    ):
        cap_ratio = GROWTH_CAP_RATIO
    else:
        cap_ratio = 1.0 if all_saturated else 2.0

    plan = optimize_allocation(
        curves=curves,
        current_spend=result.current_spend,
        total_budget=fitted_budget,
        cap_ratio=cap_ratio,
    )

    policy_plan = apply_allocation_policy(
        raw_plan=plan,
        insufficient=insufficient,
        brief=parsed_brief,
        summaries=result.summaries,
        brief_channels=parsed_brief.channels,
        curves=curves,
        planning_mode=planning_mode,
    )

    allocations = policy_plan.fitted_allocations
    confidence = "high" if curves and not insufficient else "medium" if curves else "low"
    allocation_warnings = []
    if policy_plan.expansion_budget > 0.01:
        allocation_warnings.append(
            f"{policy_plan.expansion_budget:,.0f} routed to expansion tests and reserves "
            "because fitted channels reached supported spend caps."
        )

    await write_audit_row(
        client=context.client,
        campaign_id=campaign_id,
        run_id=run_id,
        step_index=3,
        node="performance",
        summary=(
            f"Computed deterministic allocation for {len(curves)} fitted channel curves"
            f" with {policy_plan.expansion_budget:,.0f} unallocated."
        ),
        source="performance:allocation",
        confidence=confidence,
        model_used="none",
    )

    return {
        "channel_summaries": result.summaries,
        "allocations": allocations,
        "warnings": [warning.message for warning in result.warnings] + allocation_warnings,
        "ga4_warnings": result.warnings,
        "ga4_row_count": result.row_count,
        "unallocated_budget": policy_plan.expansion_budget,
        "expansion_budget": policy_plan.expansion_budget,
        "expansion_candidates": policy_plan.expansion_candidates,
        "policy_notes": policy_plan.policy_notes,
        "mmm_raw_allocations": policy_plan.mmm_raw_allocations,
        "errors": [],
    }

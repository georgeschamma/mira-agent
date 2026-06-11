from __future__ import annotations

from mira_agent.graph.context import MiraContext
from mira_agent.graph.state import MiraMediaPlanState, NodeError
from mira_agent.integrations.ga4 import CsvParseError, parse_ga4_csv
from mira_agent.repositories.campaigns import write_audit_row
from mira_agent.schemas.media_plan import MediaPlanGraphRequest
from mira_agent.services.mmm import (
    ChannelAllocation,
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

    plan = optimize_allocation(
        curves=curves,
        current_spend=result.current_spend,
        total_budget=fitted_budget,
    )
    allocations = [*plan.allocations, *insufficient]
    confidence = "high" if curves and not insufficient else "medium" if curves else "low"
    allocation_warnings = []
    if plan.unallocated_budget > 0.01:
        allocation_warnings.append(
            f"{plan.unallocated_budget:,.0f} of the requested budget was left unallocated because "
            "fitted channels reached supported spend caps."
        )

    await write_audit_row(
        client=context.client,
        campaign_id=campaign_id,
        run_id=run_id,
        step_index=3,
        node="performance",
        summary=(
            f"Computed deterministic allocation for {len(curves)} fitted channel curves"
            f" with {plan.unallocated_budget:,.0f} unallocated."
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
        "unallocated_budget": plan.unallocated_budget,
        "errors": [],
    }

from __future__ import annotations

import os
from typing import Literal

from pydantic_ai import Agent

from mira_agent.graph.context import MiraContext
from mira_agent.graph.nodes.strategy import channels_without_ga4_data
from mira_agent.graph.state import (
    ExpansionTest,
    MiraMediaPlanState,
    NodeError,
    StrategicBrief,
)
from mira_agent.repositories.campaigns import write_audit_row
from mira_agent.schemas.media_plan import SourceClaim
from mira_agent.services.mmm import ChannelAllocation


def _load_skill(name: str) -> str:
    path = os.path.abspath(__file__)
    for _ in range(5):
        path = os.path.dirname(path)
    base = path
    path = os.path.join(base, "skills", name)
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return f.read()
    return ""


def fallback_strategic_brief(
    state: MiraMediaPlanState,
    planning_mode: Literal["efficiency", "growth", "balanced"],
) -> StrategicBrief:
    brief = state["parsed_brief"]
    summaries = state.get("channel_summaries", [])
    allocations = state.get("allocations", [])
    findings = state.get("findings", [])
    segments = sorted(
        state.get("audience_segments", []),
        key=lambda item: item.count,
        reverse=True,
    )
    current_spend = sum(item.total_cost for item in summaries)
    missing_channels = state.get("expansion_candidates", []) or channels_without_ga4_data(
        brief.channels, [item.channel for item in summaries]
    )
    
    # Heuristic roles
    channel_roles = {}
    for a in allocations:
        if a.zone == "saturated" or a.zone == "insufficient_data":
            channel_roles[a.channel] = "hold"
        else:
            channel_roles[a.channel] = "harvest"
            
    # do_not_scale
    do_not_scale = [a.channel for a in allocations if a.zone == "saturated"]
    
    expansion_tests = []
    expansion_budget = state.get("expansion_budget", 0.0)
    if expansion_budget > 0.01:
        if missing_channels:
            avg_budget = expansion_budget / len(missing_channels)
            for ch in missing_channels:
                expansion_tests.append(
                    ExpansionTest(
                        channel=ch,
                        monthly_budget_range=f"${avg_budget * 0.8:,.0f}–${avg_budget * 1.2:,.0f}",
                        hypothesis=(
                            f"Testing {ch} prospecting campaigns "
                            "to build top-of-funnel reach."
                        ),
                        primary_kpi="CTR / Cost per Lead",
                        audience_fit=f"B2B target audience on {ch}",
                        source="brief:channels",
                    )
                )
        else:
            expansion_tests.append(
                ExpansionTest(
                    channel="Reserve Test Pool",
                    monthly_budget_range=(
                        f"${expansion_budget * 0.8:,.0f}–"
                        f"${expansion_budget * 1.2:,.0f}"
                    ),
                    hypothesis=(
                        "Allocate unallocated budget to a reserve pool "
                        "for future ad-hoc testing."
                    ),
                    primary_kpi="Strategic ROI / Learnings",
                    audience_fit="General target audience",
                    source="performance:allocation",
                )
            )
            
    # budget_waterfall
    budget_waterfall = []
    for a in allocations:
        if a.zone != "saturated":
            budget_waterfall.append(f"Scale {a.channel} up to optimal capacity.")
    if expansion_tests:
        budget_waterfall.append("Deploy remaining budget to expansion tests.")
    
    # situation_summary
    situation = _situation_summary(
        budget=brief.budget,
        current_spend=current_spend,
        channel_count=len(summaries),
    )
    
    # saturation_diagnosis
    saturation = _saturation_diagnosis(allocations)
    
    # source_claims
    claims = [
        SourceClaim(
            claim="Budget moves come from deterministic performance allocation.",
            source="performance:allocation",
        )
    ]
    claims.extend(
        SourceClaim(claim=f"Research signal: {item.title}", source=item.url)
        for item in findings[:3]
    )
    claims.extend(
        SourceClaim(claim=f"Audience priority: {item.label}", source=item.reference)
        for item in segments[:3]
    )
    
    return StrategicBrief(
        planning_mode=planning_mode,
        situation_summary=situation,
        saturation_diagnosis=saturation,
        channel_roles=channel_roles,
        audience_priorities=[
            f"{segment.label}: {segment.count} records ({segment.reference})"
            for segment in segments[:5]
        ],
        channel_moves=[_channel_move(item) for item in allocations],
        do_not_scale=do_not_scale,
        expansion_tests=expansion_tests,
        budget_waterfall=budget_waterfall,
        key_risks=_key_risks(state=state, missing_channels=missing_channels),
        research_insights=[
            _research_insight(title=item.title, url=item.url, highlights=item.highlights)
            for item in findings
        ],
        source_claims=claims,
        expansion_opportunities=state.get("policy_notes", []) or [],
    )


async def synthesize_node(
    state: MiraMediaPlanState, context: MiraContext
) -> MiraMediaPlanState:
    brief = state["parsed_brief"]
    summaries = state.get("channel_summaries", [])
    allocations = state.get("allocations", [])
    # No findings or segments variables needed here as they are not used
    current_spend = sum(item.total_cost for item in summaries)
    missing_channels = state.get("expansion_candidates", []) or channels_without_ga4_data(
        brief.channels, [item.channel for item in summaries]
    )
    policy_notes = state.get("policy_notes", [])
    expansion_budget = state.get("expansion_budget", 0.0)

    # Goal -> planning mode mapping (deterministic seed)
    goal_lower = brief.goal.lower()
    if any(term in goal_lower for term in ("reduce cac", "efficiency", "cut")):
        planning_mode: Literal["efficiency", "growth", "balanced"] = "efficiency"
    elif any(term in goal_lower for term in ("grow", "scale", "pipeline")):
        planning_mode = "growth"
    else:
        planning_mode = "balanced"

    # Load media planning skill
    synthesis_skill = _load_skill("media-plan-synthesis.md")

    # Structured output Agent
    agent = Agent(
        context.model,
        output_type=StrategicBrief,
        instructions=(
            "You are a strategic media synthesis assistant. Generate a "
            "StrategicBrief structured output based on the parsed brief, "
            "performance data, CRM audience segments, and web research findings. "
            "Follow the provided media planning skill guidelines.\n\n"
            f"Skill Guidelines:\n{synthesis_skill}\n\n"
            f"HARD CONSTRAINT: The planning mode must be '{planning_mode}'. "
            f"Set 'planning_mode' to exactly '{planning_mode}'."
        ),
        retries=1,
    )

    prompt = (
        "Input Data:\n"
        f"- Product: {brief.product}\n"
        f"- Target Audience: {brief.audience}\n"
        f"- Goal: {brief.goal}\n"
        f"- Requested Channels: {', '.join(brief.channels)}\n"
        f"- Brief Budget: {brief.budget}\n"
        f"- Current GA4 Spend: {current_spend:,.2f}\n"
        f"- Fitted Channel Allocations: {', '.join(_channel_move(item) for item in allocations)}\n"
        f"- Policy Notes: {', '.join(policy_notes) if policy_notes else 'None'}\n"
        f"- Expansion Budget (unallocated budget): ${expansion_budget:,.2f}\n"
        f"- Expansion Candidates (channels in brief missing GA4): {', '.join(missing_channels)}\n"
        f"- Audience Segment hints: {', '.join(state.get('audience_channel_hints', []))}\n"
        f"- Research insights: {state.get('research_insights_data')}\n\n"
        "Fill out all the fields in the StrategicBrief. Make sure to "
        "generate detailed ExpansionTest plans if expansion budget is "
        "positive and missing channels exist, utilizing any research insights."
    )

    try:
        result = await agent.run(prompt)
        strategic_brief = StrategicBrief.model_validate(result.output)
        # Force the constraint
        strategic_brief.planning_mode = planning_mode
    except Exception as exc:
        strategic_brief = fallback_strategic_brief(state, planning_mode)
        # Log LLM synthesis node failure in errors
        errors = list(state.get("errors", []))
        errors.append(
            NodeError(
                node="synthesize",
                code="LLM_SYNTHESIS_FAILED",
                message=f"LLM synthesis failed: {exc}. Using deterministic fallback.",
            )
        )
        state["errors"] = errors

    await write_audit_row(
        client=context.client,
        campaign_id=state["campaign_id"],
        run_id=state["run_id"],
        step_index=4,
        node="synthesize",
        summary="Merged research, audience, performance, and brief context into a strategic brief.",
        source="performance:allocation",
        confidence="medium" if state.get("errors") else "high",
        model_used=context.settings.llm_model or "none",
    )
    return {"strategic_brief": strategic_brief}


def _situation_summary(*, budget: int, current_spend: float, channel_count: int) -> str:
    if budget <= 0:
        return (
            f"No explicit brief budget was provided; use current GA4 spend of "
            f"{_money(current_spend)} across {channel_count} tracked channel"
            f"{'s' if channel_count != 1 else ''} as the baseline."
        )
    delta = budget - current_spend
    if abs(delta) < 0.5:
        return (
            f"Brief budget matches current GA4 spend at {_money(current_spend)} across "
            f"{channel_count} tracked channel{'s' if channel_count != 1 else ''}."
        )
    direction = "increase capacity" if delta > 0 else "reduce tracked spend"
    return (
        f"Brief budget is {_money(budget)} versus current GA4 spend of {_money(current_spend)}, "
        f"so the plan must {direction} by {_money(abs(delta))}."
    )


def _saturation_diagnosis(allocations: list[ChannelAllocation]) -> str:
    if not allocations:
        return "No fitted channel allocation was available; keep the plan explicitly directional."
    saturated = [item.channel for item in allocations if item.zone == "saturated"]
    if saturated:
        return "Saturated fitted channels: " + ", ".join(_clean(item) for item in saturated) + "."
    insufficient = [item.channel for item in allocations if item.zone == "insufficient_data"]
    if insufficient:
        return (
            "Channels without enough spend history: "
            + ", ".join(_clean(item) for item in insufficient)
            + "."
        )
    return "Fitted channels are not all saturated; explain moves by marginal ROI."


def _channel_move(allocation: ChannelAllocation) -> str:
    return (
        f"{_clean(allocation.channel)}: {_money(allocation.current_spend)} -> "
        f"{_money(allocation.recommended_spend)} "
        f"({_signed_money(allocation.delta)}, {allocation.zone}, marginal ROI "
        f"{_number(allocation.marginal_roi)})."
    )


def _key_risks(*, state: MiraMediaPlanState, missing_channels: list[str]) -> list[str]:
    risks = list(state.get("warnings", []))
    if missing_channels:
        risks.append(
            "No deterministic allocation is available for "
            + ", ".join(missing_channels)
            + " until GA4 spend history exists."
        )
    if not state.get("findings"):
        risks.append("Research returned no market signals; strategy must lean on brief and data.")
    if not state.get("allocations"):
        risks.append("Performance data did not produce fitted allocation rows.")
    return risks or ["Review assumptions after the first measured reporting cycle."]


def _research_insight(*, title: str, url: str, highlights: list[str]) -> str:
    if highlights:
        return f"{title}: {'; '.join(highlights)} ({url})"
    return f"{title}: {url}"


def _money(value: float | int | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:,.0f}"


def _signed_money(value: float | None) -> str:
    if value is None:
        return "n/a"
    sign = "+" if value > 0 else ""
    return f"{sign}{_money(value)}"


def _number(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.3f}"


def _clean(value: str) -> str:
    return value.replace("|", "/")

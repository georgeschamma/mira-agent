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
from mira_agent.services.allocation_policy import (
    SATURATED_MROI_CEILING,
    ExpansionAllocation,
    split_expansion_budget,
)
from mira_agent.services.budget_waterfall import (
    WaterfallRow,
    build_budget_waterfall,
    describe_budget_waterfall,
)
from mira_agent.services.expansion_hypothesis import (
    GENERIC_HYPOTHESIS_RE,
    build_expansion_audience_fit,
    build_expansion_hypothesis,
)
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
    expansion_allocations, reserve_pool = _expansion_split_for_state(state)
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
            
    do_not_scale = _deterministic_do_not_scale(allocations)
    
    expansion_tests = _rebuild_expansion_tests(
        state=state,
        expansion_allocations=expansion_allocations,
        llm_tests=[],
    )
            
    budget_waterfall = describe_budget_waterfall(
        _budget_waterfall_for_state(
            state=state,
            expansion_allocations=expansion_allocations,
            reserve_pool=reserve_pool,
        )
    )
    
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
        expansion_opportunities=_policy_notes_with_expansion(state, expansion_allocations),
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
    expansion_budget = state.get("expansion_budget", 0.0)
    expansion_allocations, reserve_pool = _expansion_split_for_state(state)
    policy_notes = _policy_notes_with_expansion(state, expansion_allocations)
    state["expansion_allocations"] = expansion_allocations
    state["expansion_reserve_pool"] = reserve_pool
    state["policy_notes"] = policy_notes

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
        retries=2,
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
        "- Deterministic Expansion Allocations (fixed):\n"
        f"{_expansion_allocation_block(expansion_allocations, reserve_pool, state)}\n"
        f"- Audience Segment hints: {', '.join(state.get('audience_channel_hints', []))}\n"
        f"- Research insights: {state.get('research_insights_data')}\n\n"
        "Fill out all the fields in the StrategicBrief. Budget figures per test are fixed. "
        "For each listed expansion allocation, write only hypothesis, primary_kpi, and "
        "audience_fit. Do not add duplicate expansion rows or change test budgets."
    )

    try:
        result = await agent.run(prompt)
        strategic_brief = StrategicBrief.model_validate(result.output)
        # Force the constraint
        strategic_brief.planning_mode = planning_mode
        strategic_brief.expansion_tests = _rebuild_expansion_tests(
            state=state,
            expansion_allocations=expansion_allocations,
            llm_tests=strategic_brief.expansion_tests,
        )
        strategic_brief.do_not_scale = _deterministic_do_not_scale(allocations)
        strategic_brief.budget_waterfall = describe_budget_waterfall(
            _budget_waterfall_for_state(
                state=state,
                expansion_allocations=expansion_allocations,
                reserve_pool=reserve_pool,
            )
        )
    except Exception as exc:
        strategic_brief = fallback_strategic_brief(state, planning_mode)
        strategic_brief.expansion_tests = _rebuild_expansion_tests(
            state=state,
            expansion_allocations=expansion_allocations,
            llm_tests=strategic_brief.expansion_tests,
        )
        strategic_brief.do_not_scale = _deterministic_do_not_scale(allocations)
        strategic_brief.budget_waterfall = describe_budget_waterfall(
            _budget_waterfall_for_state(
                state=state,
                expansion_allocations=expansion_allocations,
                reserve_pool=reserve_pool,
            )
        )
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
    return {
        "strategic_brief": strategic_brief,
        "expansion_allocations": expansion_allocations,
        "expansion_reserve_pool": reserve_pool,
        "policy_notes": policy_notes,
    }


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


def _expansion_split_for_state(
    state: MiraMediaPlanState,
) -> tuple[list[ExpansionAllocation], float]:
    brief = state["parsed_brief"]
    summaries = state.get("channel_summaries", [])
    candidates = state.get("expansion_candidates", []) or channels_without_ga4_data(
        brief.channels,
        [item.channel for item in summaries],
    )
    insights = state.get("research_insights_data")
    suggested = insights.suggested_test_channels if insights else []
    max_fitted_spend = max(
        (item.recommended_spend for item in state.get("allocations", [])),
        default=0.0,
    )
    return split_expansion_budget(
        state.get("expansion_budget", 0.0),
        candidates,
        state.get("audience_channel_hints", []),
        suggested,
        max_fitted_spend,
    )


def _budget_waterfall_for_state(
    *,
    state: MiraMediaPlanState,
    expansion_allocations: list[ExpansionAllocation],
    reserve_pool: float,
) -> list[WaterfallRow]:
    return build_budget_waterfall(
        brief_budget=state["parsed_brief"].budget,
        fitted_total=sum(item.recommended_spend for item in state.get("allocations", [])),
        expansion_allocations=expansion_allocations,
        reserve_pool=reserve_pool,
    )


def _rebuild_expansion_tests(
    *,
    state: MiraMediaPlanState,
    expansion_allocations: list[ExpansionAllocation],
    llm_tests: list[ExpansionTest],
) -> list[ExpansionTest]:
    by_channel: dict[str, ExpansionTest] = {}
    for test in llm_tests:
        key = _expansion_channel_key(test.channel)
        if key and key not in by_channel:
            by_channel[key] = test

    tests: list[ExpansionTest] = []
    for allocation in expansion_allocations:
        matched = by_channel.get(_expansion_channel_key(allocation.channel))
        use_fallback_hypothesis = (
            matched is None or GENERIC_HYPOTHESIS_RE.search(matched.hypothesis)
        )
        tests.append(
            ExpansionTest(
                channel=allocation.channel,
                monthly_budget_range=_currency(allocation.phase1_test_budget),
                hypothesis=(
                    matched.hypothesis
                    if matched and not use_fallback_hypothesis
                    else build_expansion_hypothesis(
                        allocation.channel,
                        state.get("audience_segments", []),
                        state.get("findings", []),
                        state["parsed_brief"].audience,
                    )
                ),
                primary_kpi=matched.primary_kpi if matched else "Qualified leads; CAC",
                audience_fit=(
                    matched.audience_fit
                    if matched and not use_fallback_hypothesis
                    else build_expansion_audience_fit(
                        allocation.channel,
                        state.get("audience_segments", []),
                        state["parsed_brief"].audience,
                    )
                ),
                source=_source_for_expansion_channel(allocation.channel, state),
            )
        )
    return tests


def _deterministic_do_not_scale(allocations: list[ChannelAllocation]) -> list[str]:
    return [
        item.channel
        for item in allocations
        if item.zone == "saturated" and (item.marginal_roi or 0.0) < SATURATED_MROI_CEILING
    ]


def _policy_notes_with_expansion(
    state: MiraMediaPlanState,
    expansion_allocations: list[ExpansionAllocation],
) -> list[str]:
    notes = list(state.get("policy_notes", []))
    for allocation in expansion_allocations:
        if allocation.weight_notes not in notes:
            notes.append(allocation.weight_notes)
    return notes


def _expansion_allocation_block(
    expansion_allocations: list[ExpansionAllocation],
    reserve_pool: float,
    state: MiraMediaPlanState,
) -> str:
    if not expansion_allocations:
        return f"- No channel-specific expansion tests. Reserve pool: {_currency(reserve_pool)}."
    lines = [
        (
            f"- {allocation.channel}: phase 1 {_currency(allocation.phase1_test_budget)}, "
            f"staged reserve {_currency(allocation.staged_reserve)}. "
            f"{allocation.weight_notes} "
            f"Research cue: {_expansion_research_cue(allocation.channel, state)}"
        )
        for allocation in expansion_allocations
    ]
    lines.append(
        f"- Unassigned reserve pool: {_currency(reserve_pool)}; release only after KPI gates."
    )
    return "\n".join(lines)


def _expansion_research_cue(channel: str, state: MiraMediaPlanState) -> str:
    finding = _matching_expansion_finding(channel, state)
    if finding is None:
        return "none"
    highlight = finding.highlights[0] if finding.highlights else finding.title
    return highlight[:120]


def _matching_expansion_finding(channel: str, state: MiraMediaPlanState):
    terms = _source_terms_for_channel(channel)
    for finding in state.get("findings", []):
        haystack = " ".join([finding.title, *finding.highlights]).lower()
        if any(term in haystack for term in terms):
            return finding
    findings = state.get("findings", [])
    return findings[0] if findings else None


def _source_for_expansion_channel(channel: str, state: MiraMediaPlanState) -> str:
    terms = _source_terms_for_channel(channel)
    for finding in state.get("findings", []):
        haystack = " ".join([finding.title, *finding.highlights]).lower()
        if any(term in haystack for term in terms):
            return finding.url
    return "brief:channels"


def _source_terms_for_channel(channel: str) -> set[str]:
    key = _expansion_channel_key(channel)
    aliases = {
        "meta": {"meta", "facebook", "instagram"},
        "x": {"x", "twitter"},
    }
    return aliases.get(key, {key})


def _expansion_channel_key(value: str) -> str:
    text = " ".join(
        value.lower()
        .replace("|", " ")
        .replace("/", " ")
        .replace("-", " ")
        .replace("_", " ")
        .split()
    )
    aliases = {
        "facebook": "meta",
        "fb": "meta",
        "instagram": "meta",
        "ig": "meta",
        "twitter": "x",
    }
    known = (
        "meta",
        "tiktok",
        "linkedin",
        "google",
        "youtube",
        "reddit",
        "x",
        "bing",
        "programmatic",
        "podcast",
        "webinar",
    )
    for token in text.split():
        channel = aliases.get(token, token)
        if channel in known:
            return channel
    return text[:40].strip()


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


def _currency(value: float | int | None) -> str:
    if value is None:
        return "n/a"
    return f"${value:,.0f}"


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

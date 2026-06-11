from __future__ import annotations

import os
import re
import time
from dataclasses import asdict

from pydantic import BaseModel, Field
from pydantic_ai import Agent

from mira_agent.graph.context import MiraContext
from mira_agent.graph.state import ExpansionTest, MiraMediaPlanState, NodeError, StrategicBrief
from mira_agent.repositories.campaigns import write_audit_row
from mira_agent.repositories.media_plans import save_media_plan_document
from mira_agent.schemas.media_plan import MediaPlanGraphRequest, SourceClaim
from mira_agent.services.allocation_policy import ExpansionAllocation
from mira_agent.services.mmm import ChannelAllocation, allocation_to_dict
from mira_agent.services.sources import validate_source_ref


class StrategyNarrativeOutput(BaseModel):
    executive_summary: str
    audience_strategy: str
    channel_rationale: str
    expansion_opportunities: str
    sequencing: str
    risks: str
    claims: list[SourceClaim] = Field(min_length=1)


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


def render_recommended_tests_table(
    tests: list[ExpansionTest],
    expansion_allocations: list[ExpansionAllocation] | None = None,
    reserve_pool: float = 0.0,
) -> str:
    reserve_line = (
        f"\n\nReserve pool: {_money(reserve_pool)} held until phase-1 tests clear KPI gates."
        if reserve_pool > 0.01
        else ""
    )
    if not tests:
        return "No recommended tests at this time." + reserve_line
    allocation_by_channel = {
        allocation.channel: allocation for allocation in (expansion_allocations or [])
    }
    rows = [
        (
            "| Channel | Phase-1 monthly test budget | Staged reserve | Hypothesis | "
            "Primary KPI | Source |"
        ),
        "|---|---:|---:|---|---|---|",
    ]
    for test in tests:
        staged_reserve = allocation_by_channel.get(test.channel)
        rows.append(
            f"| {test.channel} | {test.monthly_budget_range} | "
            f"{_money(staged_reserve.staged_reserve) if staged_reserve else 'n/a'} | "
            f"{test.hypothesis} | {test.primary_kpi} | {test.source} |"
        )
    return "\n".join(rows) + reserve_line


async def strategy_node(state: MiraMediaPlanState, context: MiraContext) -> MiraMediaPlanState:
    campaign_id = state["campaign_id"]
    run_id = state["run_id"]
    started_at = state.get("started_at", time.perf_counter())
    request = MediaPlanGraphRequest.model_validate(state["media_input"])

    retries = state.get("strategy_retries", 0)
    state["strategy_retries"] = retries + 1

    table = render_budget_table(state.get("allocations", []))
    narrative = await generate_strategy_narrative(state=state, context=context, budget_table=table)
    validate_source_claims(narrative.claims)
    fallback_used = _strategy_fallback_used(state)
    model_used = "deterministic-fallback" if fallback_used else context.settings.llm_model or "none"
    document = render_media_plan_document(
        state=state,
        request=request,
        table=table,
        narrative=narrative,
    )
    processing_ms = int((time.perf_counter() - started_at) * 1000)

    strategic_brief = state.get("strategic_brief")
    expansion_tests_serializable = []
    if strategic_brief:
        for t in strategic_brief.expansion_tests:
            expansion_tests_serializable.append({
                "channel": t.channel,
                "monthly_budget_range": t.monthly_budget_range,
                "hypothesis": t.hypothesis,
                "primary_kpi": t.primary_kpi,
                "audience_fit": t.audience_fit,
                "source": t.source,
            })

    metadata = {
        "crm_file": {
            "filename": request.crm_filename,
            "row_count": state.get("crm_row_count", 0),
            "segment_count": len(state.get("audience_segments", [])),
        },
        "ga4_file": {
            "filename": request.ga4_filename,
            "row_count": state.get("ga4_row_count", 0),
            "channel_count": len(state.get("channel_summaries", [])),
        },
        "warning_count": len(state.get("warnings", [])),
        "source_claims": [claim.model_dump() for claim in narrative.claims],
        "allocations": [allocation_to_dict(item) for item in state.get("allocations", [])],
        "strategic_brief": (
            state["strategic_brief"].model_dump() if state.get("strategic_brief") else None
        ),
        "expansion_tests": expansion_tests_serializable,
        "expansion_budget": state.get("expansion_budget", 0.0),
        "expansion_allocations": [
            asdict(item) for item in state.get("expansion_allocations", [])
        ],
        "expansion_reserve_pool": state.get("expansion_reserve_pool", 0.0),
        "policy_notes": state.get("policy_notes", []),
        "mmm_raw_allocations": [
            allocation_to_dict(item)
            for item in state.get("mmm_raw_allocations", [])
        ],
    }

    ids = await save_media_plan_document(
        client=context.client,
        campaign_id=campaign_id,
        run_id=run_id,
        document_markdown=document,
        document_metadata=metadata,
        model_used=model_used,
        processing_ms=processing_ms,
    )
    await write_audit_row(
        client=context.client,
        campaign_id=campaign_id,
        run_id=run_id,
        step_index=5,
        node="strategy",
        summary=(
            "Created sourced fallback media-plan document with deterministic budget table."
            if fallback_used
            else "Created sourced media-plan document with deterministic budget table."
        ),
        source="performance:allocation",
        confidence="low" if fallback_used else "medium" if state.get("errors") else "high",
        model_used=model_used,
    )

    return {
        "action_sheet_id": ids.action_sheet_id,
        "approval_id": ids.approval_id,
        "document_markdown": document,
        "document_metadata": metadata,
        "processing_ms": processing_ms,
    }


async def generate_strategy_narrative(
    *,
    state: MiraMediaPlanState,
    context: MiraContext,
    budget_table: str,
) -> StrategyNarrativeOutput:
    strategy_skill = _load_skill("media-plan-strategy.md")
    agent = Agent(
        context.model,
        output_type=StrategyNarrativeOutput,
        instructions=(
            "Write concise media-plan narrative sections. Budget numbers are fixed facts from "
            "the prompt; explain them but do not invent or change them. Use the strategic "
            "synthesis brief as the primary source for situation, audience, channel moves, "
            "risks, and expansion candidates. If the brief lists channels without GA4 "
            "performance data, treat them as narrative-only expansion candidates outside the "
            "deterministic allocation table. Every claim source must start with https://, "
            "brief:, crm:segment:, ga4:, or performance:.\n\n"
            f"Strategy Guidelines:\n{strategy_skill}"
        ),
        retries=2,
    )
    try:
        result = await agent.run(_strategy_prompt(state=state, budget_table=budget_table))
        output = StrategyNarrativeOutput.model_validate(result.output)
        validate_source_claims(output.claims)
        return output
    except Exception:
        _record_strategy_fallback(state)
        return fallback_narrative(state)


def _record_strategy_fallback(state: MiraMediaPlanState) -> None:
    errors = list(state.get("errors", []))
    errors.append(
        NodeError(
            node="strategy",
            code="LLM_STRUCTURED_OUTPUT_UNAVAILABLE",
            message="Structured LLM output was unavailable; used sourced fallback narrative.",
        )
    )
    state["errors"] = errors


def _strategy_fallback_used(state: MiraMediaPlanState) -> bool:
    return any(
        error.node == "strategy" and error.code == "LLM_STRUCTURED_OUTPUT_UNAVAILABLE"
        for error in state.get("errors", [])
    )


def fallback_narrative(state: MiraMediaPlanState) -> StrategyNarrativeOutput:
    strategic_brief = state.get("strategic_brief")
    if strategic_brief:
        return StrategyNarrativeOutput(
            executive_summary=strategic_brief.situation_summary,
            audience_strategy=_fallback_list(
                strategic_brief.audience_priorities,
                "Prioritize aggregate CRM segments without exposing row-level PII.",
            ),
            channel_rationale=_fallback_list(
                strategic_brief.channel_moves,
                "Shift spend according to marginal ROI and saturation status.",
            ),
            expansion_opportunities=_fallback_list(
                strategic_brief.expansion_opportunities,
                (
                    "Treat brief-requested channels without GA4 history as narrative-only "
                    "test candidates."
                ),
            ),
            sequencing="Launch deterministic channel moves first, then review measured tests.",
            risks=_fallback_list(
                strategic_brief.key_risks,
                "Channels with insufficient spend history are held or flagged for review.",
            ),
            claims=strategic_brief.source_claims
            or [
                SourceClaim(
                    claim="Budget allocation comes from deterministic performance math.",
                    source="performance:allocation",
                )
            ],
        )

    first_segment = (
        state.get("audience_segments", [])[0].reference
        if state.get("audience_segments")
        else "brief:audience"
    )
    first_research = (
        state.get("findings", [])[0].url
        if state.get("findings")
        else "brief:raw"
    )
    return StrategyNarrativeOutput(
        executive_summary="Use the deterministic allocation table as the media-plan baseline.",
        audience_strategy=(
            "Prioritize the largest CRM lifecycle segments without exposing row-level PII."
        ),
        channel_rationale="Shift spend according to marginal ROI and saturation status.",
        expansion_opportunities=(
            "Treat brief-requested channels without GA4 history as narrative-only test candidates; "
            "do not add them to the deterministic allocation table until spend history exists."
        ),
        sequencing=(
            "Launch the highest-confidence channel moves first, then review sparse channels."
        ),
        risks="Channels with insufficient spend history are held or flagged for review.",
        claims=[
            SourceClaim(
                claim="Budget allocation comes from deterministic performance math.",
                source="performance:allocation",
            ),
            SourceClaim(
                claim="Audience strategy uses aggregate CRM segments only.",
                source=first_segment,
            ),
            SourceClaim(
                claim="Research context uses sourced market signals when available.",
                source=first_research,
            ),
        ],
    )


def render_media_plan_document(
    *,
    state: MiraMediaPlanState,
    request: MediaPlanGraphRequest,
    table: str,
    narrative: StrategyNarrativeOutput,
) -> str:
    brief = state["parsed_brief"]
    warnings = state.get("warnings", [])
    claims = "\n".join(f"- {claim.claim} ({claim.source})" for claim in narrative.claims)
    budget_context = render_budget_context(state)
    parse_warnings = _parse_warnings(warnings)
    warning_lines = (
        "\n".join(f"- {warning}" for warning in parse_warnings) if parse_warnings else "- None"
    )

    strategic_brief = state.get("strategic_brief")
    expansion_tests_list = strategic_brief.expansion_tests if strategic_brief else []
    recommended_tests_table = render_recommended_tests_table(
        expansion_tests_list,
        state.get("expansion_allocations", []),
        state.get("expansion_reserve_pool", 0.0),
    )

    return "\n".join(
        [
            f"# Media Plan - {brief.product}",
            "",
            "## Executive Summary",
            narrative.executive_summary,
            "",
            "## Budget Context",
            budget_context,
            "",
            "## Budget Allocation",
            table,
            "",
            "## Recommended Tests",
            recommended_tests_table,
            "",
            "## Audience Strategy",
            narrative.audience_strategy,
            "",
            "## Channel Rationale",
            narrative.channel_rationale,
            "",
            "## Expansion Opportunities",
            narrative.expansion_opportunities,
            "",
            "## Sequencing & Timing",
            narrative.sequencing,
            "",
            "## Risks & Assumptions",
            narrative.risks,
            "",
            "## Sources & Audit",
            claims,
            "",
            "## Parse Warnings",
            warning_lines,
            "",
            "## Input Metadata",
            f"- CRM file: {request.crm_filename}",
            f"- GA4 file: {request.ga4_filename}",
        ]
    ).strip() + "\n"


def render_budget_context(state: MiraMediaPlanState) -> str:
    brief = state["parsed_brief"]
    summaries = state.get("channel_summaries", [])
    allocations = state.get("allocations", [])
    current_spend = sum(item.total_cost for item in summaries)
    missing_channels = channels_without_ga4_data(
        brief.channels, [item.channel for item in summaries]
    )
    saturated_channels = [item.channel for item in allocations if item.zone == "saturated"]
    budget_warnings = _budget_warnings(state.get("warnings", []))
    saturated_label = (
        ", ".join(_cell(item) for item in saturated_channels) if saturated_channels else "None"
    )

    expansion_budget = state.get("expansion_budget", 0.0)
    policy_notes = state.get("policy_notes", [])

    lines = [
        f"- Brief budget: {_money(brief.budget) if brief.budget > 0 else 'not provided'}",
        f"- Current GA4 spend: {_money(current_spend)}",
        f"- Net budget change required: {_budget_delta_label(brief.budget, current_spend)}",
        f"- Expansion budget available: {_money(expansion_budget)}",
        (
            "- Policy adjustments: "
            + (
                "; ".join(_cell(n) for n in policy_notes)
                if policy_notes
                else "None"
            )
        ),
        (
            f"- GA4 channels with performance data: {len(summaries)}"
            f"{_list_suffix([item.channel for item in summaries])}"
        ),
        (
            f"- Fitted allocation rows: {len(allocations)}"
            f"{_list_suffix([item.channel for item in allocations])}"
        ),
        f"- Saturated fitted channels: {saturated_label}",
        (
            "- Brief channels without GA4 data: "
            f"{', '.join(_cell(item) for item in missing_channels) if missing_channels else 'None'}"
        ),
    ]
    if budget_warnings:
        lines.append(
            "- Budget warnings: " + " ".join(_cell(warning) for warning in budget_warnings)
        )
    return "\n".join(lines)


def render_budget_table(allocations: list[ChannelAllocation]) -> str:
    if not allocations:
        return "No fitted channel allocation was available. Review GA4 spend history."

    rows = [
        "| Channel | Current Spend | Recommended Spend | Delta | Zone | Marginal ROI |",
        "|---|---:|---:|---:|---|---:|",
    ]
    for allocation in allocations:
        rows.append(
            f"| {_cell(allocation.channel)} | {_money(allocation.current_spend)} | "
            f"{_money(allocation.recommended_spend)} | {_money(allocation.delta)} | "
            f"{allocation.zone} | {_number(allocation.marginal_roi)} |"
        )
    return "\n".join(rows)


def validate_source_claims(claims: list[SourceClaim]) -> None:
    for claim in claims:
        validate_source_ref(claim.source)


def _strategy_prompt(*, state: MiraMediaPlanState, budget_table: str) -> str:
    brief = state["parsed_brief"]
    budget_context = render_budget_context(state)
    strategic_brief = state.get("strategic_brief")
    missing_channels = channels_without_ga4_data(
        brief.channels, [item.channel for item in state.get("channel_summaries", [])]
    )
    findings = "\n".join(
        f"- {item.title}: {item.url}"
        f"{_highlights_suffix(item.highlights)}"
        for item in state.get("findings", [])
    )
    segments = "\n".join(
        f"- {item.label}: {item.count} ({item.reference})"
        for item in state.get("audience_segments", [])
    )
    summaries = "\n".join(
        f"- {item.channel}: cost={item.total_cost}, response={item.total_response}, "
        f"source={item.source_ref}"
        for item in state.get("channel_summaries", [])
    )
    remediation = state.get("strategy_remediation", "")
    remediation_block = (
        f"REMEDIATION CONTEXT FROM PREVIOUS ATTEMPT:\n{remediation}\n\n"
        if remediation
        else ""
    )
    hints = state.get("audience_channel_hints", [])
    hints_block = f"Audience channel hints: {', '.join(hints)}\n" if hints else ""
    expansion_budget = state.get("expansion_budget", 0.0)

    return (
        f"{remediation_block}"
        "Parsed brief:\n"
        f"- Product: {brief.product}\n"
        f"- Audience: {brief.audience}\n"
        f"- Goal: {brief.goal}\n"
        f"- Channels requested: {', '.join(brief.channels) or 'paid media'}\n"
        f"- Budget: {_money(brief.budget) if brief.budget > 0 else 'not provided'}\n\n"
        "Budget context:\n"
        f"{budget_context}\n\n"
        f"Expansion budget available: {_money(expansion_budget)}\n"
        f"{hints_block}\n"
        "Strategic synthesis brief:\n"
        f"{_strategic_brief_block(strategic_brief)}\n\n"
        "Fixed budget table:\n"
        f"{budget_table}\n\n"
        "Research signals:\n"
        f"{findings or '- none'}\n\n"
        "Audience segments:\n"
        f"{segments or '- none'}\n\n"
        "GA4 performance summaries:\n"
        f"{summaries or '- none'}\n\n"
        "Expansion candidates outside the deterministic table:\n"
        f"{', '.join(missing_channels) if missing_channels else 'None'}\n\n"
        "Return narrative sections only. Do not output alternative spend numbers. "
        "Do not add expansion candidates to the deterministic allocation table; discuss them "
        "as qualitative tests until GA4 spend history exists."
    )


def _strategic_brief_block(strategic_brief: StrategicBrief | None) -> str:
    if strategic_brief is None:
        return "- none"

    test_lines = []
    for t in strategic_brief.expansion_tests:
        test_lines.append(
            f"    - Channel: {t.channel}, "
            f"Budget Range: {t.monthly_budget_range}, "
            f"Hypothesis: {t.hypothesis}, "
            f"KPI: {t.primary_kpi}"
        )
    test_block = "\n".join(test_lines) if test_lines else "    - none"

    return "\n".join(
        [
            f"- Situation: {strategic_brief.situation_summary}",
            f"- Saturation diagnosis: {strategic_brief.saturation_diagnosis}",
            f"- Planning Mode: {strategic_brief.planning_mode}",
            f"- Channel roles: {strategic_brief.channel_roles}",
            f"- Do Not Scale channels: {strategic_brief.do_not_scale}",
            f"- Budget Waterfall: {strategic_brief.budget_waterfall}",
            "- Audience priorities:\n"
            f"{_bullet_block(strategic_brief.audience_priorities)}",
            "- Channel moves:\n"
            f"{_bullet_block(strategic_brief.channel_moves)}",
            "- Recommended Tests:\n"
            f"{test_block}",
            "- Key risks:\n"
            f"{_bullet_block(strategic_brief.key_risks)}",
            "- Research insights:\n"
            f"{_bullet_block(strategic_brief.research_insights)}",
            "- Synthesis sources:\n"
            f"{_source_claim_block(strategic_brief.source_claims)}",
        ]
    )


def _bullet_block(items: list[str]) -> str:
    return "\n".join(f"  - {item}" for item in items) if items else "  - none"


def _source_claim_block(claims: list[SourceClaim]) -> str:
    return "\n".join(f"  - {claim.claim} ({claim.source})" for claim in claims) or "  - none"


def _fallback_list(items: list[str], fallback: str) -> str:
    return " ".join(items) if items else fallback


def channels_without_ga4_data(brief_channels: list[str], ga4_channels: list[str]) -> list[str]:
    return [
        channel
        for channel in brief_channels
        if _has_meaningful_channel_tokens(channel)
        and not any(_channel_matches(channel, ga4_channel) for ga4_channel in ga4_channels)
    ]


def _channel_matches(brief_channel: str, ga4_channel: str) -> bool:
    ga4_text = _normalized_channel_text(ga4_channel)
    phrase = _normalized_channel_text(brief_channel)
    if phrase and phrase in ga4_text:
        return True
    return any(token in ga4_text for token in _channel_tokens(brief_channel))


def _channel_tokens(value: str) -> list[str]:
    aliases = {
        "fb": ("facebook", "meta"),
        "instagram": ("instagram", "meta", "facebook"),
        "meta": ("meta", "facebook", "instagram"),
    }
    stopwords = {"ad", "ads", "channel", "channels", "campaign", "media", "paid"}
    tokens: list[str] = []
    for token in _normalized_channel_text(value).split():
        if len(token) <= 2 or token in stopwords:
            continue
        tokens.append(token)
        tokens.extend(aliases.get(token, ()))
    return sorted(set(tokens))


def _has_meaningful_channel_tokens(value: str) -> bool:
    return bool(_channel_tokens(value))


def _normalized_channel_text(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def _budget_delta_label(brief_budget: int, current_spend: float) -> str:
    if brief_budget <= 0:
        return "No explicit budget; using current GA4 spend baseline"
    delta = brief_budget - current_spend
    if abs(delta) < 0.5:
        return "No net change"
    direction = "increase available" if delta > 0 else "reduction required"
    return f"{_money(abs(delta))} {direction}"


def _budget_warnings(warnings: list[str]) -> list[str]:
    budget_terms = ("budget", "fitted channel", "allocation")
    return [
        warning for warning in warnings if any(term in warning.lower() for term in budget_terms)
    ]


def _parse_warnings(warnings: list[str]) -> list[str]:
    budget_warning_set = set(_budget_warnings(warnings))
    return [warning for warning in warnings if warning not in budget_warning_set]


def _list_suffix(items: list[str]) -> str:
    return f" ({', '.join(_cell(item) for item in items)})" if items else ""


def _highlights_suffix(highlights: list[str]) -> str:
    return f" Highlights: {'; '.join(highlights)}" if highlights else ""


def _money(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:,.0f}"


def _number(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.3f}"


def _cell(value: str) -> str:
    return value.replace("|", "/")

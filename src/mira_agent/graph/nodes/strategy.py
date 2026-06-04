from __future__ import annotations

import time

from pydantic import BaseModel, Field
from pydantic_ai import Agent

from mira_agent.graph.context import MiraContext
from mira_agent.graph.state import MiraMediaPlanState, NodeError
from mira_agent.repositories.campaigns import finish_campaign_run, write_audit_row
from mira_agent.repositories.media_plans import save_media_plan_document
from mira_agent.schemas.media_plan import MediaPlanGraphRequest, SourceClaim
from mira_agent.services.mmm import ChannelAllocation, allocation_to_dict

ALLOWED_SOURCE_PREFIXES = ("https://", "brief:", "crm:segment:", "ga4:", "performance:")


class StrategyNarrativeOutput(BaseModel):
    executive_summary: str
    audience_strategy: str
    channel_rationale: str
    sequencing: str
    risks: str
    claims: list[SourceClaim] = Field(min_length=1)


async def strategy_node(state: MiraMediaPlanState, context: MiraContext) -> MiraMediaPlanState:
    campaign_id = state["campaign_id"]
    run_id = state["run_id"]
    started_at = state.get("started_at", time.perf_counter())
    request = MediaPlanGraphRequest.model_validate(state["media_input"])

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
        step_index=4,
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
    await finish_campaign_run(
        client=context.client,
        run_id=run_id,
        status="partial" if state.get("errors") else "done",
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
    agent = Agent(
        context.model,
        output_type=StrategyNarrativeOutput,
        instructions=(
            "Write concise media-plan narrative sections. Budget numbers are fixed facts from "
            "the prompt; explain them but do not invent or change them. Every claim source must "
            "start with https://, brief:, crm:segment:, ga4:, or performance:."
        ),
        retries=1,
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
    warning_lines = "\n".join(f"- {warning}" for warning in warnings) if warnings else "- None"

    return "\n".join(
        [
            f"# Media Plan - {brief.product}",
            "",
            "## Executive Summary",
            narrative.executive_summary,
            "",
            "## Budget Allocation",
            table,
            "",
            "## Audience Strategy",
            narrative.audience_strategy,
            "",
            "## Channel Rationale",
            narrative.channel_rationale,
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
        if not claim.source.startswith(ALLOWED_SOURCE_PREFIXES):
            raise ValueError(f"Unsupported strategy source: {claim.source}")


def _strategy_prompt(*, state: MiraMediaPlanState, budget_table: str) -> str:
    findings = "\n".join(f"- {item.title}: {item.url}" for item in state.get("findings", []))
    segments = "\n".join(
        f"- {item.label}: {item.count} ({item.reference})"
        for item in state.get("audience_segments", [])
    )
    summaries = "\n".join(
        f"- {item.channel}: cost={item.total_cost}, response={item.total_response}, "
        f"source={item.source_ref}"
        for item in state.get("channel_summaries", [])
    )
    return (
        "Fixed budget table:\n"
        f"{budget_table}\n\n"
        "Research signals:\n"
        f"{findings or '- none'}\n\n"
        "Audience segments:\n"
        f"{segments or '- none'}\n\n"
        "GA4 performance summaries:\n"
        f"{summaries or '- none'}\n\n"
        "Return narrative sections only. Do not output alternative spend numbers."
    )


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

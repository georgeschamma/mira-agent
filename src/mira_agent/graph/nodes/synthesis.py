from __future__ import annotations

from mira_agent.graph.context import MiraContext
from mira_agent.graph.nodes.strategy import channels_without_ga4_data
from mira_agent.graph.state import MiraMediaPlanState, StrategicBrief
from mira_agent.repositories.campaigns import write_audit_row
from mira_agent.schemas.media_plan import SourceClaim
from mira_agent.services.mmm import ChannelAllocation


async def synthesize_node(
    state: MiraMediaPlanState, context: MiraContext
) -> MiraMediaPlanState:
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
    missing_channels = channels_without_ga4_data(
        brief.channels, [item.channel for item in summaries]
    )

    strategic_brief = StrategicBrief(
        situation_summary=_situation_summary(
            budget=brief.budget,
            current_spend=current_spend,
            channel_count=len(summaries),
        ),
        saturation_diagnosis=_saturation_diagnosis(allocations),
        audience_priorities=[
            f"{segment.label}: {segment.count} records ({segment.reference})"
            for segment in segments[:5]
        ],
        channel_moves=[_channel_move(item) for item in allocations],
        expansion_opportunities=[
            f"{channel}: requested in the brief but missing from GA4; discuss as a "
            "narrative-only test until spend history exists."
            for channel in missing_channels
        ],
        key_risks=_key_risks(state=state, missing_channels=missing_channels),
        research_insights=[
            _research_insight(title=item.title, url=item.url, highlights=item.highlights)
            for item in findings
        ],
        source_claims=_source_claims(
            findings=findings,
            allocations=allocations,
            segments=segments,
            missing_channels=missing_channels,
        ),
    )

    await write_audit_row(
        client=context.client,
        campaign_id=state["campaign_id"],
        run_id=state["run_id"],
        step_index=4,
        node="synthesize",
        summary="Merged research, audience, performance, and brief context into a strategic brief.",
        source="performance:allocation",
        confidence="medium" if state.get("errors") else "high",
        model_used="none",
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


def _source_claims(
    *,
    findings,
    allocations: list[ChannelAllocation],
    segments,
    missing_channels: list[str],
) -> list[SourceClaim]:
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
    if missing_channels:
        claims.append(
            SourceClaim(
                claim="Brief requested channels that are missing from GA4 spend history.",
                source="brief:channels",
            )
        )
    if any(item.zone == "insufficient_data" for item in allocations):
        claims.append(
            SourceClaim(
                claim="Some channels lack enough spend history for deterministic fitting.",
                source="ga4:csv",
            )
        )
    return claims


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

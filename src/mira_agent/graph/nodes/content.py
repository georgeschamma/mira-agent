from __future__ import annotations

import time

from pydantic import BaseModel, Field
from pydantic_ai import Agent

from mira_agent.exceptions import ApiError
from mira_agent.graph.context import MiraContext
from mira_agent.graph.state import MiraState, ResearchFinding
from mira_agent.repositories.campaigns import (
    create_action_sheet_with_approvals,
    finish_campaign_run,
    write_audit_row,
)
from mira_agent.schemas.analyze import AnalyzeRequest, Recommendation

INVALID_SOURCES = {"", "model reasoning", "llm", "none", "n/a", "unknown"}
BRIEF_SOURCES = {
    "brief:product",
    "brief:audience",
    "brief:channels",
    "brief:budget",
    "brief:goal",
}


class ContentNodeOutput(BaseModel):
    recommendations: list[Recommendation] = Field(min_length=2, max_length=4)


async def content_node(state: MiraState, context: MiraContext) -> MiraState:
    campaign_id = state["campaign_id"]
    run_id = state["run_id"]
    started_at = state.get("started_at", time.perf_counter())

    try:
        recommendations = await generate_recommendations(state, context)
        assert_valid_sources(recommendations)
        processing_ms = int((time.perf_counter() - started_at) * 1000)
        sheet_ids = await create_action_sheet_with_approvals(
            client=context.client,
            campaign_id=campaign_id,
            run_id=run_id,
            recommendations=recommendations,
            model_used=context.settings.llm_model,
            processing_ms=processing_ms,
        )
        await write_audit_row(
            client=context.client,
            campaign_id=campaign_id,
            run_id=run_id,
            step_index=2,
            node="content",
            summary=f"Created {len(recommendations)} sourced recommendations.",
            source=recommendations[0].source,
            confidence="medium" if state.get("errors") else "high",
            model_used=context.settings.llm_model,
        )
        await finish_campaign_run(
            client=context.client,
            run_id=run_id,
            status="partial" if state.get("errors") else "done",
        )
    except ApiError as exc:
        await _mark_content_error(state=state, context=context, error=exc.message)
        raise
    except Exception as exc:
        await _mark_content_error(
            state=state,
            context=context,
            error="Content generation failed.",
        )
        raise ApiError(
            "CONTENT_GENERATION_FAILED",
            "Could not generate sourced recommendations.",
            500,
        ) from exc

    return {
        "action_sheet_id": sheet_ids.action_sheet_id,
        "approval_id": sheet_ids.approval_id,
        "recommendations": recommendations,
        "processing_ms": processing_ms,
    }


async def generate_recommendations(state: MiraState, context: MiraContext) -> list[Recommendation]:
    request = AnalyzeRequest.model_validate(state["request"])
    findings = state.get("findings", [])
    agent = Agent(
        context.model,
        output_type=ContentNodeOutput,
        instructions=(
            "Return 2 to 4 concrete marketing recommendations. "
            "Each source must be an exact Exa URL from the prompt or one of the brief:* fields. "
            "Use impact='high' for at least one recommendation that should require Admin approval."
        ),
        retries=2,
    )
    result = await agent.run(_build_content_prompt(request=request, findings=findings))
    output = ContentNodeOutput.model_validate(result.output)
    recommendations = _normalize_recommendations(
        output.recommendations,
        findings=findings,
    )
    if not recommendations:
        raise ApiError("CONTENT_EMPTY", "The content node returned no recommendations.", 500)
    return recommendations


def assert_valid_sources(recommendations: list[Recommendation]) -> None:
    for recommendation in recommendations:
        source = recommendation.source.strip()
        if source.lower() in INVALID_SOURCES:
            raise ApiError(
                "UNSOURCED_RECOMMENDATION",
                "Every recommendation needs a concrete source.",
                500,
            )
        if not source.startswith(("http://", "https://", "brief:")):
            raise ApiError(
                "UNSOURCED_RECOMMENDATION",
                "Every recommendation source must be a URL or brief field.",
                500,
            )


def _normalize_recommendations(
    recommendations: list[Recommendation],
    *,
    findings: list[ResearchFinding],
) -> list[Recommendation]:
    normalized: list[Recommendation] = []
    seen_ids: set[str] = set()
    for index, recommendation in enumerate(recommendations, start=1):
        recommendation_id = _normalize_recommendation_id(recommendation.id, index, seen_ids)
        source = _match_source(recommendation.source, findings)
        normalized.append(
            recommendation.model_copy(
                update={
                    "id": recommendation_id,
                    "source": source,
                    "needs_approval": recommendation.impact == "high",
                }
            )
        )

    if normalized and not any(item.needs_approval for item in normalized):
        first = normalized[0]
        normalized[0] = first.model_copy(update={"impact": "high", "needs_approval": True})
    return normalized


def _normalize_recommendation_id(raw_id: str, index: int, seen_ids: set[str]) -> str:
    candidate = raw_id.strip() if raw_id else f"rec_{index}"
    if candidate in seen_ids:
        candidate = f"{candidate}_{index}"
    seen_ids.add(candidate)
    return candidate


def _match_source(source: str, findings: list[ResearchFinding]) -> str:
    raw_source = source.strip()
    source_lower = raw_source.lower()
    for brief_source in BRIEF_SOURCES:
        if source_lower == brief_source:
            return brief_source

    for finding in findings:
        if finding.url in raw_source:
            return finding.url
        if finding.title and finding.title.lower() in source_lower:
            return finding.url

    return raw_source


def _build_content_prompt(*, request: AnalyzeRequest, findings: list[ResearchFinding]) -> str:
    evidence = "\n".join(
        _format_finding(index, finding) for index, finding in enumerate(findings, 1)
    )
    if not evidence:
        evidence = "No Exa findings were returned. Use brief:* sources only."

    return (
        "Campaign brief:\n"
        f"- brief:product = {request.product}\n"
        f"- brief:audience = {request.audience}\n"
        f"- brief:channels = {', '.join(request.channels)}\n"
        f"- brief:budget = {request.budget}\n"
        f"- brief:goal = {request.goal}\n\n"
        "Exa evidence:\n"
        f"{evidence}\n\n"
        "Recommendation requirements:\n"
        "- Return 2 to 4 recommendations.\n"
        "- Use domains from: research, audience, analytics, creative, media, content.\n"
        "- Use effort and impact from: low, medium, high.\n"
        "- Set source to an exact URL shown above or an exact brief:* source.\n"
        "- At least one recommendation should be high impact."
    )


def _format_finding(index: int, finding: ResearchFinding) -> str:
    highlights = " | ".join(finding.highlights[:3]) if finding.highlights else "No highlights."
    return f"{index}. {finding.title}\n   URL: {finding.url}\n   Highlights: {highlights}"


async def _mark_content_error(*, state: MiraState, context: MiraContext, error: str) -> None:
    campaign_id = state.get("campaign_id")
    run_id = state.get("run_id")
    if not campaign_id or not run_id:
        return

    try:
        await write_audit_row(
            client=context.client,
            campaign_id=campaign_id,
            run_id=run_id,
            step_index=2,
            node="content",
            summary=error,
            source="pydanticai",
            confidence="low",
            model_used=context.settings.llm_model,
        )
        await finish_campaign_run(
            client=context.client,
            run_id=run_id,
            status="error",
            error=error,
        )
    except ApiError:
        return

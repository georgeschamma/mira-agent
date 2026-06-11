from __future__ import annotations

from pydantic_ai import Agent

from mira_agent.graph.context import MiraContext
from mira_agent.graph.state import (
    MiraState,
    NodeError,
    ResearchFinding,
    ResearchInsights,
)
from mira_agent.repositories.campaigns import write_audit_row
from mira_agent.schemas.analyze import AnalyzeRequest


def build_research_query(request: AnalyzeRequest) -> str:
    channels = ", ".join(request.channels)
    return (
        f"Marketing campaign research for {request.product}. "
        f"Audience: {request.audience}. Channels: {channels}. "
        f"Goal: {request.goal}. Budget: {request.budget}."
    )


async def extract_research_insights(
    findings: list[ResearchFinding],
    context: MiraContext,
) -> ResearchInsights:
    if not findings:
        return ResearchInsights()

    agent = Agent(
        context.model,
        output_type=ResearchInsights,
        instructions=(
            "Extract structured research insights from the given web search findings. "
            "Identify specific channel benchmarks "
            "(platform name, metrics like CTR/CPC/conversion rate, "
            "range of values, source URL), "
            "strategic signals (market trends, buyer behaviors), and suggested test channels. "
            "All source URLs must be copied exactly from the findings."
        ),
        retries=1,
    )
    try:
        findings_text = "\n\n".join(
            f"Title: {f.title}\nURL: {f.url}\nHighlights:\n"
            + "\n".join(f"- {h}" for h in f.highlights)
            for f in findings
        )
        result = await agent.run(findings_text)
        return ResearchInsights.model_validate(result.output)
    except Exception:
        return ResearchInsights()


async def research_node(state: MiraState, context: MiraContext) -> MiraState:
    request = AnalyzeRequest.model_validate(state["request"])
    campaign_id = state["campaign_id"]
    run_id = state["run_id"]
    errors = list(state.get("errors", []))

    try:
        findings = await context.research_client.search(
            build_research_query(request),
            num_results=context.settings.exa_num_results,
        )
    except Exception:
        errors.append(
            NodeError(
                node="research",
                code="RESEARCH_FAILED",
                message="Exa research failed; content will fall back to brief sources.",
            )
        )
        await _write_research_audit(
            context=context,
            campaign_id=campaign_id,
            run_id=run_id,
            findings=[],
            confidence="low",
            summary="Exa research failed; continuing with brief-only sources.",
        )
        return {"findings": [], "research_insights_data": ResearchInsights(), "errors": errors}

    confidence = "medium" if findings else "low"
    if not findings:
        errors.append(
            NodeError(
                node="research",
                code="RESEARCH_EMPTY",
                message="Exa returned no results; content will fall back to brief sources.",
            )
        )

    summary = (
        f"Found {len(findings)} sourced market signal{'s' if len(findings) != 1 else ''}."
        if findings
        else "Exa returned no market signals; continuing with brief-only sources."
    )
    await _write_research_audit(
        context=context,
        campaign_id=campaign_id,
        run_id=run_id,
        findings=findings,
        confidence=confidence,
        summary=summary,
    )

    insights = await extract_research_insights(findings, context)

    return {"findings": findings, "research_insights_data": insights, "errors": errors}


async def _write_research_audit(
    *,
    context: MiraContext,
    campaign_id: str,
    run_id: str,
    findings: list[ResearchFinding],
    confidence: str,
    summary: str,
) -> None:
    source = findings[0].url if findings else "exa"
    await write_audit_row(
        client=context.client,
        campaign_id=campaign_id,
        run_id=run_id,
        step_index=1,
        node="research",
        summary=summary,
        source=source,
        confidence=confidence,
        model_used="none",
    )


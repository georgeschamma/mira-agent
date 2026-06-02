from __future__ import annotations

from mira_agent.graph.context import MiraContext
from mira_agent.graph.state import MiraState, NodeError, ResearchFinding
from mira_agent.repositories.campaigns import write_audit_row
from mira_agent.schemas.analyze import AnalyzeRequest


def build_research_query(request: AnalyzeRequest) -> str:
    channels = ", ".join(request.channels)
    return (
        f"Marketing campaign research for {request.product}. "
        f"Audience: {request.audience}. Channels: {channels}. "
        f"Goal: {request.goal}. Budget: {request.budget}."
    )


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
        return {"findings": [], "errors": errors}

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
    return {"findings": findings, "errors": errors}


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

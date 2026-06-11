from __future__ import annotations

from dataclasses import asdict
from typing import Any

from langgraph.graph import END, START, StateGraph

from mira_agent.config import Settings, get_settings
from mira_agent.exceptions import ApiError
from mira_agent.graph.context import MiraContext
from mira_agent.graph.nodes.audience import audience_node
from mira_agent.graph.nodes.brief import brief_node
from mira_agent.graph.nodes.content import content_node
from mira_agent.graph.nodes.performance import performance_node
from mira_agent.graph.nodes.research import research_node
from mira_agent.graph.nodes.router import router_node
from mira_agent.graph.nodes.strategy import strategy_node
from mira_agent.graph.nodes.synthesis import synthesize_node
from mira_agent.graph.state import MiraMediaPlanState, MiraState
from mira_agent.integrations.exa import ExaResearchClient, ResearchClient
from mira_agent.integrations.llm import get_model
from mira_agent.repositories.rls_client import RlsClient
from mira_agent.schemas.analyze import AnalyzeRequest, AnalyzeResponse
from mira_agent.schemas.auth import CurrentUser
from mira_agent.schemas.media_plan import (
    AudienceSegmentResponse,
    BudgetAllocationResponse,
    ChannelSummaryResponse,
    FileMetadata,
    MediaPlanGraphRequest,
    MediaPlanResponse,
    ParseWarningResponse,
)
from mira_agent.services.mmm import allocation_to_dict


def build_thin_graph(context: MiraContext):
    builder = StateGraph(MiraState)

    async def route(state: MiraState) -> MiraState:
        return await router_node(state, context)

    async def research(state: MiraState) -> MiraState:
        return await research_node(state, context)

    async def content(state: MiraState) -> MiraState:
        return await content_node(state, context)

    builder.add_node("router", route)
    builder.add_node("research", research)
    builder.add_node("content", content)
    builder.add_edge(START, "router")
    builder.add_edge("router", "research")
    builder.add_edge("research", "content")
    builder.add_edge("content", END)
    return builder.compile()


def build_media_plan_graph(context: MiraContext):
    builder = StateGraph(MiraMediaPlanState)

    async def brief(state: MiraMediaPlanState) -> MiraMediaPlanState:
        return await brief_node(state, context)

    async def research(state: MiraMediaPlanState) -> MiraMediaPlanState:
        return await research_node(state, context)  # type: ignore[arg-type]

    async def audience(state: MiraMediaPlanState) -> MiraMediaPlanState:
        return await audience_node(state, context)

    async def performance(state: MiraMediaPlanState) -> MiraMediaPlanState:
        return await performance_node(state, context)

    async def synthesize(state: MiraMediaPlanState) -> MiraMediaPlanState:
        return await synthesize_node(state, context)

    async def strategy(state: MiraMediaPlanState) -> MiraMediaPlanState:
        return await strategy_node(state, context)

    builder.add_node("brief", brief)
    builder.add_node("research", research)
    builder.add_node("audience", audience)
    builder.add_node("performance", performance)
    builder.add_node("synthesize", synthesize)
    builder.add_node("strategy", strategy)
    builder.add_edge(START, "brief")
    builder.add_edge("brief", "research")
    builder.add_edge("brief", "audience")
    builder.add_edge("brief", "performance")
    builder.add_edge("research", "synthesize")
    builder.add_edge("audience", "synthesize")
    builder.add_edge("performance", "synthesize")
    builder.add_edge("synthesize", "strategy")
    builder.add_edge("strategy", END)
    return builder.compile()


async def run_mira_analysis(
    *,
    client: RlsClient,
    request: AnalyzeRequest,
    user: CurrentUser,
    settings: Settings | None = None,
    research_client: ResearchClient | None = None,
    model: Any | None = None,
) -> AnalyzeResponse:
    resolved_settings = settings or get_settings()
    if research_client is None and not resolved_settings.has_exa_config:
        raise ApiError(
            "INTEGRATION_NOT_CONFIGURED",
            "Exa settings are required before running analysis.",
            500,
        )
    if model is None and not resolved_settings.has_llm_config:
        raise ApiError(
            "INTEGRATION_NOT_CONFIGURED",
            "LLM settings are required before running analysis.",
            500,
        )

    context = MiraContext(
        client=client,
        user=user,
        settings=resolved_settings,
        research_client=research_client or ExaResearchClient(api_key=resolved_settings.exa_api_key),
        model=model or get_model(resolved_settings),
    )
    graph = build_thin_graph(context)
    final_state = await graph.ainvoke(
        {
            "request": request.model_dump(),
            "user_id": user.id,
        }
    )

    recommendations = final_state.get("recommendations") or []
    if not recommendations:
        raise ApiError("CONTENT_EMPTY", "The analysis produced no recommendations.", 500)

    return AnalyzeResponse(
        campaign_id=final_state["campaign_id"],
        run_id=final_state["run_id"],
        action_sheet_id=final_state["action_sheet_id"],
        approval_id=final_state.get("approval_id"),
        recommendations=recommendations,
    )


async def run_media_plan_analysis(
    *,
    client: RlsClient,
    request: MediaPlanGraphRequest,
    user: CurrentUser,
    settings: Settings | None = None,
    research_client: ResearchClient | None = None,
    model: Any | None = None,
) -> MediaPlanResponse:
    resolved_settings = settings or get_settings()
    if research_client is None and not resolved_settings.has_exa_config:
        raise ApiError(
            "INTEGRATION_NOT_CONFIGURED",
            "Exa settings are required before running a media plan.",
            500,
        )
    if model is None and not resolved_settings.has_llm_config:
        raise ApiError(
            "INTEGRATION_NOT_CONFIGURED",
            "LLM settings are required before running a media plan.",
            500,
        )

    context = MiraContext(
        client=client,
        user=user,
        settings=resolved_settings,
        research_client=research_client or ExaResearchClient(api_key=resolved_settings.exa_api_key),
        model=model or get_model(resolved_settings),
    )
    graph = build_media_plan_graph(context)
    final_state = await graph.ainvoke(
        {
            "request": request.model_dump(),
            "user_id": user.id,
        }
    )

    return MediaPlanResponse(
        campaign_id=final_state["campaign_id"],
        run_id=final_state["run_id"],
        action_sheet_id=final_state["action_sheet_id"],
        approval_id=final_state.get("approval_id"),
        document_markdown=final_state["document_markdown"],
        document_status="pending",
        approvals=["pending"] if final_state.get("approval_id") else [],
        crm_file=FileMetadata(
            filename=request.crm_filename,
            row_count=final_state.get("crm_row_count", 0),
            warnings=[
                ParseWarningResponse.model_validate(asdict(warning))
                for warning in final_state.get("crm_warnings", [])
            ],
        ),
        ga4_file=FileMetadata(
            filename=request.ga4_filename,
            row_count=final_state.get("ga4_row_count", 0),
            warnings=[
                ParseWarningResponse.model_validate(asdict(warning))
                for warning in final_state.get("ga4_warnings", [])
            ],
        ),
        audience_segments=[
            AudienceSegmentResponse.model_validate(asdict(item))
            for item in final_state.get("audience_segments", [])
        ],
        channel_summaries=[
            ChannelSummaryResponse.model_validate(asdict(item))
            for item in final_state.get("channel_summaries", [])
        ],
        allocations=[
            BudgetAllocationResponse.model_validate(allocation_to_dict(item))
            for item in final_state.get("allocations", [])
        ],
    )

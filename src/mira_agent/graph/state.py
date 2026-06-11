from __future__ import annotations

import operator
from typing import Annotated, Any, NotRequired, TypedDict

from pydantic import BaseModel, Field

from mira_agent.integrations.crm import AudienceSegment
from mira_agent.integrations.ga4 import ChannelPerformanceSummary, CsvParseWarning
from mira_agent.schemas.analyze import Recommendation
from mira_agent.schemas.media_plan import SourceClaim
from mira_agent.services.mmm import ChannelAllocation


class ResearchFinding(BaseModel):
    title: str
    url: str
    highlights: list[str] = Field(default_factory=list)
    published_date: str | None = None


class NodeError(BaseModel):
    node: str
    code: str
    message: str


class MiraState(TypedDict):
    request: dict[str, Any]
    user_id: str
    campaign_id: NotRequired[str]
    run_id: NotRequired[str]
    action_sheet_id: NotRequired[str]
    approval_id: NotRequired[str | None]
    findings: NotRequired[list[ResearchFinding]]
    recommendations: NotRequired[list[Recommendation]]
    errors: NotRequired[list[NodeError]]
    model_used: NotRequired[str]
    started_at: NotRequired[float]
    processing_ms: NotRequired[int]


class ParsedMediaBrief(BaseModel):
    org_id: str
    product: str
    audience: str
    channels: list[str]
    budget: int
    goal: str
    raw_brief: str


class StrategicBrief(BaseModel):
    situation_summary: str
    saturation_diagnosis: str
    audience_priorities: list[str] = Field(default_factory=list)
    channel_moves: list[str] = Field(default_factory=list)
    expansion_opportunities: list[str] = Field(default_factory=list)
    key_risks: list[str] = Field(default_factory=list)
    research_insights: list[str] = Field(default_factory=list)
    source_claims: list[SourceClaim] = Field(default_factory=list)


class MiraMediaPlanState(TypedDict):
    request: dict[str, Any]
    media_input: NotRequired[dict[str, Any]]
    user_id: str
    campaign_id: NotRequired[str]
    run_id: NotRequired[str]
    action_sheet_id: NotRequired[str]
    approval_id: NotRequired[str | None]
    parsed_brief: NotRequired[ParsedMediaBrief]
    strategic_brief: NotRequired[StrategicBrief]
    findings: Annotated[list[ResearchFinding], operator.add]
    audience_segments: Annotated[list[AudienceSegment], operator.add]
    channel_summaries: Annotated[list[ChannelPerformanceSummary], operator.add]
    allocations: Annotated[list[ChannelAllocation], operator.add]
    errors: Annotated[list[NodeError], operator.add]
    warnings: Annotated[list[str], operator.add]
    crm_warnings: Annotated[list[CsvParseWarning], operator.add]
    ga4_warnings: Annotated[list[CsvParseWarning], operator.add]
    crm_row_count: NotRequired[int]
    ga4_row_count: NotRequired[int]
    unallocated_budget: NotRequired[float]
    document_markdown: NotRequired[str]
    document_metadata: NotRequired[dict[str, Any]]
    model_used: NotRequired[str]
    started_at: NotRequired[float]
    processing_ms: NotRequired[int]

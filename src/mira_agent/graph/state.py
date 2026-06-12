from __future__ import annotations

import operator
from typing import Annotated, Any, Literal, NotRequired, TypedDict

from pydantic import BaseModel, Field, field_validator

from mira_agent.integrations.crm import AudienceSegment
from mira_agent.integrations.ga4 import ChannelPerformanceSummary, CsvParseWarning
from mira_agent.schemas.analyze import Recommendation
from mira_agent.schemas.media_plan import SourceClaim
from mira_agent.services.allocation_policy import ExpansionAllocation
from mira_agent.services.mmm import ChannelAllocation
from mira_agent.services.sources import validate_source_ref


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


class ChannelBenchmark(BaseModel):
    platform: str
    metric: str
    range: str
    source_url: str


class ResearchInsights(BaseModel):
    channel_benchmarks: list[ChannelBenchmark] = Field(default_factory=list)
    strategic_signals: list[str] = Field(default_factory=list)
    suggested_test_channels: list[str] = Field(default_factory=list)


class ExpansionTest(BaseModel):
    channel: str = Field(
        description="Channel name only, lowercase, e.g. 'meta'. No sentences.",
        max_length=40,
    )
    monthly_budget_range: str      # e.g. "$1,500–$2,500"
    hypothesis: str = Field(description="One sentence, max 25 words.", max_length=220)
    primary_kpi: str = Field(
        description="One primary KPI, optionally one secondary.",
        max_length=100,
    )
    audience_fit: str
    source: str                    # https:// or brief:

    @field_validator("source")
    @classmethod
    def source_must_be_reference(cls, value: str) -> str:
        return validate_source_ref(value)


class StrategicBrief(BaseModel):
    planning_mode: Literal["efficiency", "growth", "balanced"] = "balanced"
    situation_summary: str
    saturation_diagnosis: str
    # channel -> harvest|nurture|test|hold
    channel_roles: dict[str, str] = Field(default_factory=dict)
    audience_priorities: list[str] = Field(default_factory=list)
    channel_moves: list[str] = Field(default_factory=list)        # from policy output
    do_not_scale: list[str] = Field(
        default_factory=list,
        description="Channel names only - this field is set deterministically.",
    )
    expansion_tests: list[ExpansionTest] = Field(default_factory=list)
    budget_waterfall: list[str] = Field(default_factory=list)     # ordered spend priorities
    key_risks: list[str] = Field(default_factory=list)
    research_insights: list[str] = Field(default_factory=list)
    source_claims: list[SourceClaim] = Field(default_factory=list)
    expansion_opportunities: list[str] = Field(default_factory=list)  # retained for compatibility


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
    
    # New state variables
    expansion_budget: NotRequired[float]
    expansion_candidates: NotRequired[list[str]]
    expansion_allocations: NotRequired[list[ExpansionAllocation]]
    expansion_reserve_pool: NotRequired[float]
    policy_notes: NotRequired[list[str]]
    mmm_raw_allocations: NotRequired[list[ChannelAllocation]]
    research_insights_data: NotRequired[ResearchInsights]
    audience_channel_hints: NotRequired[list[str]]
    strategy_retries: NotRequired[int]
    critic_failed: NotRequired[bool]
    strategy_remediation: NotRequired[str]

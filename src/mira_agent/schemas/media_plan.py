from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from mira_agent.schemas.analyze import ApprovalStatus

DocumentStatus = Literal["draft", "pending", "approved", "rejected"]


class ParseWarningResponse(BaseModel):
    row_number: int | None = None
    code: str
    message: str


class FileMetadata(BaseModel):
    filename: str
    row_count: int
    warnings: list[ParseWarningResponse] = Field(default_factory=list)


class AudienceSegmentResponse(BaseModel):
    reference: str
    label: str
    count: int
    dimension: str
    value: str


class ChannelSummaryResponse(BaseModel):
    channel: str
    row_count: int
    total_cost: float
    total_response: float
    unique_spend_points: int
    sufficient_data: bool
    source_ref: str


class BudgetAllocationResponse(BaseModel):
    channel: str
    current_spend: float | None
    recommended_spend: float | None
    delta: float | None
    projected_response: float | None
    marginal_roi: float | None
    zone: str


class SourceClaim(BaseModel):
    claim: str
    source: str


class ExpansionTestResponse(BaseModel):
    channel: str
    monthly_budget_range: str
    hypothesis: str
    primary_kpi: str
    audience_fit: str
    source: str


class MediaPlanGraphRequest(BaseModel):
    org_id: str
    brief: str = Field(min_length=1)
    crm_csv_text: str
    crm_filename: str
    ga4_csv_text: str
    ga4_filename: str


class MediaPlanResponse(BaseModel):
    campaign_id: str
    run_id: str
    action_sheet_id: str
    approval_id: str | None = None
    document_markdown: str
    document_status: DocumentStatus
    approvals: list[ApprovalStatus] = Field(default_factory=list)
    crm_file: FileMetadata
    ga4_file: FileMetadata
    audience_segments: list[AudienceSegmentResponse]
    channel_summaries: list[ChannelSummaryResponse]
    allocations: list[BudgetAllocationResponse]
    expansion_tests: list[ExpansionTestResponse] = Field(default_factory=list)
    expansion_budget: float = 0.0
    policy_notes: list[str] = Field(default_factory=list)
    mmm_raw_allocations: list[BudgetAllocationResponse] = Field(default_factory=list)


class MediaPlanDocument(BaseModel):
    document_markdown: str
    document_metadata: dict[str, object]
    document_status: DocumentStatus = "pending"


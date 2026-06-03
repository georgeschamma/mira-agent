from typing import Literal

from pydantic import BaseModel

from mira_agent.schemas.analyze import AnalyzeRequest, ApprovalStatus, Recommendation


class RuntimeConfigResponse(BaseModel):
    app_name: str
    app_version: str
    supabase_url: str
    supabase_anon_key: str


class ApprovalState(BaseModel):
    recommendation_id: str
    status: ApprovalStatus
    approved_by: str | None = None
    approved_at: str | None = None
    created_at: str | None = None


class ActionSheetReportResponse(BaseModel):
    action_sheet_id: str
    campaign_id: str
    run_id: str
    org_id: str
    brief: AnalyzeRequest
    recommendations: list[Recommendation]
    approvals: list[ApprovalState]
    model_used: str
    processing_ms: int | None = None
    created_at: str | None = None


class AuditRowResponse(BaseModel):
    id: str
    campaign_id: str
    run_id: str
    step_index: int
    node: str
    summary: str
    source: str | None = None
    confidence: Literal["high", "medium", "low"] | None = None
    pii_accessed: bool
    model_used: str | None = None
    created_at: str | None = None


class AuditTraceResponse(BaseModel):
    run_id: str
    rows: list[AuditRowResponse]

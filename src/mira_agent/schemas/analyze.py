from typing import Literal

from pydantic import BaseModel, Field

Domain = Literal["research", "audience", "analytics", "creative", "media", "content"]
ApprovalStatus = Literal["pending", "approved", "rejected"]


class AnalyzeRequest(BaseModel):
    org_id: str
    product: str = Field(min_length=1)
    audience: str = Field(min_length=1)
    channels: list[str] = Field(min_length=1)
    budget: int = Field(ge=0)
    goal: str = Field(min_length=1)


class Recommendation(BaseModel):
    id: str
    domain: Domain
    finding: str
    source: str
    effort: Literal["low", "medium", "high"]
    impact: Literal["low", "medium", "high"]
    action: str
    needs_approval: bool


class AnalyzeResponse(BaseModel):
    campaign_id: str
    run_id: str
    action_sheet_id: str
    approval_id: str | None
    recommendations: list[Recommendation]


class ApprovalRequest(BaseModel):
    status: Literal["approved", "rejected"]


class ApprovalResponse(BaseModel):
    action_sheet_id: str
    recommendation_id: str
    status: ApprovalStatus


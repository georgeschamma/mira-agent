from __future__ import annotations

from typing import Any, NotRequired, TypedDict

from pydantic import BaseModel, Field

from mira_agent.schemas.analyze import Recommendation


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

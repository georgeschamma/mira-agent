from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from mira_agent.exceptions import ApiError
from mira_agent.repositories.rls_client import PostgrestError, RlsClient
from mira_agent.schemas.analyze import AnalyzeRequest, Recommendation
from mira_agent.schemas.auth import CurrentUser


@dataclass(frozen=True, slots=True)
class CampaignRunIds:
    campaign_id: str
    run_id: str


@dataclass(frozen=True, slots=True)
class ActionSheetIds:
    action_sheet_id: str
    approval_id: str | None


async def create_campaign_run(
    *,
    client: RlsClient,
    request: AnalyzeRequest,
    user: CurrentUser,
) -> CampaignRunIds:
    campaign_id = str(uuid4())
    run_id = str(uuid4())
    now = datetime.now(UTC).isoformat()

    try:
        await client.insert(
            "campaigns",
            {
                "id": campaign_id,
                "org_id": request.org_id,
                "created_by": user.id,
                "brief": request.model_dump(),
            },
        )
        await client.insert(
            "campaign_runs",
            {
                "id": run_id,
                "campaign_id": campaign_id,
                "status": "running",
                "started_at": now,
            },
        )
        await client.update(
            "campaigns",
            {"latest_run_id": run_id},
            filters={"id": f"eq.{campaign_id}"},
        )
    except PostgrestError as exc:
        raise ApiError(
            "DB_WRITE_FAILED",
            "Could not create the campaign run through RLS.",
            500,
        ) from exc

    return CampaignRunIds(campaign_id=campaign_id, run_id=run_id)


async def write_audit_row(
    *,
    client: RlsClient,
    campaign_id: str,
    run_id: str,
    step_index: int,
    node: str,
    summary: str,
    source: str,
    confidence: str,
    model_used: str,
    pii_accessed: bool = False,
) -> None:
    try:
        await client.insert(
            "audit_log",
            {
                "campaign_id": campaign_id,
                "run_id": run_id,
                "step_index": step_index,
                "node": node,
                "summary": summary,
                "source": source,
                "confidence": confidence,
                "pii_accessed": pii_accessed,
                "model_used": model_used,
            },
        )
    except PostgrestError as exc:
        raise ApiError(
            "DB_WRITE_FAILED",
            "Could not write the audit row through RLS.",
            500,
        ) from exc


async def create_action_sheet_with_approvals(
    *,
    client: RlsClient,
    campaign_id: str,
    run_id: str,
    recommendations: list[Recommendation],
    model_used: str,
    processing_ms: int,
) -> ActionSheetIds:
    action_sheet_id = str(uuid4())
    first_approval_id: str | None = None

    try:
        await client.insert(
            "action_sheets",
            {
                "id": action_sheet_id,
                "campaign_id": campaign_id,
                "run_id": run_id,
                "recommendations": [item.model_dump() for item in recommendations],
                "model_used": model_used,
                "processing_ms": processing_ms,
            },
        )
        for recommendation in recommendations:
            if not recommendation.needs_approval:
                continue

            approval_id = str(uuid4())
            first_approval_id = first_approval_id or approval_id
            await client.insert(
                "action_sheet_approvals",
                {
                    "id": approval_id,
                    "action_sheet_id": action_sheet_id,
                    "recommendation_id": recommendation.id,
                    "status": "pending",
                },
            )
    except PostgrestError as exc:
        raise ApiError(
            "DB_WRITE_FAILED",
            "Could not create the action sheet through RLS.",
            500,
        ) from exc

    return ActionSheetIds(action_sheet_id=action_sheet_id, approval_id=first_approval_id)


async def finish_campaign_run(
    *,
    client: RlsClient,
    run_id: str,
    status: str,
    error: str | None = None,
) -> None:
    payload: dict[str, str | None] = {
        "status": status,
        "completed_at": datetime.now(UTC).isoformat(),
    }
    if error:
        payload["error"] = error[:1000]

    try:
        await client.update(
            "campaign_runs",
            payload,
            filters={"id": f"eq.{run_id}"},
        )
    except PostgrestError as exc:
        raise ApiError(
            "DB_WRITE_FAILED",
            "Could not update the campaign run through RLS.",
            500,
        ) from exc

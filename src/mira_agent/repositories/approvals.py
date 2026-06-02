from __future__ import annotations

from datetime import UTC, datetime

from mira_agent.exceptions import ApiError
from mira_agent.repositories.rls_client import PostgrestError, RlsClient
from mira_agent.schemas.analyze import ApprovalResponse, ApprovalStatus
from mira_agent.schemas.auth import CurrentUser


async def get_action_sheet_org_id(*, client: RlsClient, action_sheet_id: str) -> str:
    rows = await client.select(
        "action_sheets",
        select="id,campaigns!inner(org_id)",
        filters={"id": f"eq.{action_sheet_id}"},
        limit=1,
    )
    if not rows:
        raise ApiError("ACTION_SHEET_NOT_FOUND", "Action sheet was not found.", 404)

    campaign = rows[0].get("campaigns") or {}
    org_id = campaign.get("org_id")
    if not org_id:
        raise ApiError("ACTION_SHEET_NOT_FOUND", "Action sheet organization was not found.", 404)
    return str(org_id)


async def update_approval_status(
    *,
    client: RlsClient,
    action_sheet_id: str,
    recommendation_id: str,
    status: ApprovalStatus,
    user: CurrentUser,
) -> ApprovalResponse:
    try:
        rows = await client.update(
            "action_sheet_approvals",
            {
                "status": status,
                "approved_by": user.id,
                "approved_at": datetime.now(UTC).isoformat(),
            },
            filters={
                "action_sheet_id": f"eq.{action_sheet_id}",
                "recommendation_id": f"eq.{recommendation_id}",
            },
        )
    except PostgrestError as exc:
        raise ApiError("APPROVAL_FORBIDDEN", "Approval update was rejected by RLS.", 403) from exc

    if not rows:
        raise ApiError("APPROVAL_NOT_FOUND", "Approval row was not found.", 404)

    row = rows[0]
    return ApprovalResponse(
        action_sheet_id=str(row["action_sheet_id"]),
        recommendation_id=str(row["recommendation_id"]),
        status=row["status"],
    )


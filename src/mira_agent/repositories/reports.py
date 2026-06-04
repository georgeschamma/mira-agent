from __future__ import annotations

from typing import Any

from mira_agent.exceptions import ApiError
from mira_agent.repositories.rls_client import PostgrestError, RlsClient
from mira_agent.schemas.analyze import AnalyzeRequest, Recommendation
from mira_agent.schemas.report import (
    ActionSheetReportResponse,
    ApprovalState,
    AuditRowResponse,
    AuditTraceResponse,
)


async def fetch_action_sheet_report(
    *, client: RlsClient, action_sheet_id: str
) -> ActionSheetReportResponse:
    try:
        rows = await client.select(
            "action_sheets",
            select=(
                "id,campaign_id,run_id,recommendations,model_used,processing_ms,"
                "document_markdown,document_metadata,document_status,created_at,"
                "campaigns!inner(org_id,brief)"
            ),
            filters={"id": f"eq.{action_sheet_id}"},
            limit=1,
        )
    except PostgrestError as exc:
        raise ApiError("ACTION_SHEET_NOT_FOUND", "Action sheet was not found.", 404) from exc

    if not rows:
        raise ApiError("ACTION_SHEET_NOT_FOUND", "Action sheet was not found.", 404)

    row = rows[0]
    campaign = row.get("campaigns") or {}
    try:
        approvals = await _fetch_approval_states(client=client, action_sheet_id=action_sheet_id)
        return ActionSheetReportResponse(
            action_sheet_id=str(row["id"]),
            campaign_id=str(row["campaign_id"]),
            run_id=str(row["run_id"]),
            org_id=str(campaign["org_id"]),
            brief=AnalyzeRequest.model_validate(campaign["brief"]),
            recommendations=[
                Recommendation.model_validate(item) for item in row.get("recommendations", [])
            ],
            approvals=approvals,
            model_used=str(row["model_used"]),
            processing_ms=row.get("processing_ms"),
            document_markdown=row.get("document_markdown"),
            document_metadata=row.get("document_metadata"),
            document_status=row.get("document_status"),
            created_at=row.get("created_at"),
        )
    except KeyError as exc:
        raise ApiError(
            "ACTION_SHEET_NOT_FOUND",
            "Action sheet metadata was not found.",
            404,
        ) from exc


async def fetch_audit_trace(*, client: RlsClient, run_id: str) -> AuditTraceResponse:
    try:
        rows = await client.select(
            "audit_log",
            select=(
                "id,campaign_id,run_id,step_index,node,summary,source,confidence,"
                "pii_accessed,model_used,created_at"
            ),
            filters={"run_id": f"eq.{run_id}"},
            order="step_index.asc,created_at.asc",
        )
    except PostgrestError as exc:
        raise ApiError("AUDIT_TRACE_NOT_FOUND", "Audit trace was not found.", 404) from exc

    if not rows:
        raise ApiError("AUDIT_TRACE_NOT_FOUND", "Audit trace was not found.", 404)

    ordered_rows = sorted(
        rows,
        key=lambda item: (
            int(item.get("step_index") or 0),
            str(item.get("created_at") or ""),
        ),
    )
    return AuditTraceResponse(
        run_id=run_id,
        rows=[AuditRowResponse.model_validate(row) for row in ordered_rows],
    )


async def _fetch_approval_states(*, client: RlsClient, action_sheet_id: str) -> list[ApprovalState]:
    try:
        rows = await client.select(
            "action_sheet_approvals",
            select="recommendation_id,status,approved_by,approved_at,created_at",
            filters={"action_sheet_id": f"eq.{action_sheet_id}"},
            order="recommendation_id.asc",
        )
    except PostgrestError as exc:
        raise ApiError(
            "ACTION_SHEET_NOT_FOUND",
            "Action sheet approvals were not found.",
            404,
        ) from exc

    return [ApprovalState.model_validate(_stringify_uuid_fields(row)) for row in rows]


def _stringify_uuid_fields(row: dict[str, Any]) -> dict[str, Any]:
    return {
        **row,
        "approved_by": str(row["approved_by"]) if row.get("approved_by") else None,
    }

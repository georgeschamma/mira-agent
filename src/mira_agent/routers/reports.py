from typing import Annotated

from fastapi import APIRouter, Depends

from mira_agent.dependencies import get_rls_client, require_user
from mira_agent.repositories.reports import fetch_action_sheet_report, fetch_audit_trace
from mira_agent.repositories.rls_client import RlsClient
from mira_agent.schemas.auth import CurrentUser
from mira_agent.schemas.report import ActionSheetReportResponse, AuditTraceResponse

router = APIRouter(prefix="/api", tags=["reports"])

UserDep = Annotated[CurrentUser, Depends(require_user)]
RlsClientDep = Annotated[RlsClient, Depends(get_rls_client)]


@router.get("/action-sheets/{action_sheet_id}", response_model=ActionSheetReportResponse)
async def get_action_sheet_report(
    action_sheet_id: str,
    user: UserDep,
    client: RlsClientDep,
) -> ActionSheetReportResponse:
    return await fetch_action_sheet_report(client=client, action_sheet_id=action_sheet_id)


@router.get("/runs/{run_id}/audit", response_model=AuditTraceResponse)
async def get_run_audit_trace(
    run_id: str,
    user: UserDep,
    client: RlsClientDep,
) -> AuditTraceResponse:
    return await fetch_audit_trace(client=client, run_id=run_id)

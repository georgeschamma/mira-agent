from typing import Annotated

from fastapi import APIRouter, Depends

from mira_agent.dependencies import get_rls_client, get_write_client, require_org_role, require_user
from mira_agent.repositories.approvals import get_action_sheet_org_id, update_approval_status
from mira_agent.repositories.rls_client import RlsClient
from mira_agent.schemas.analyze import ApprovalRequest, ApprovalResponse
from mira_agent.schemas.auth import CurrentUser

router = APIRouter(prefix="/api", tags=["approvals"])

UserDep = Annotated[CurrentUser, Depends(require_user)]
RlsClientDep = Annotated[RlsClient, Depends(get_rls_client)]
WriteClientDep = Annotated[RlsClient, Depends(get_write_client)]


@router.post(
    "/action-sheets/{action_sheet_id}/approvals/{recommendation_id}",
    response_model=ApprovalResponse,
)
async def approve_recommendation(
    action_sheet_id: str,
    recommendation_id: str,
    request: ApprovalRequest,
    user: UserDep,
    client: RlsClientDep,
    write_client: WriteClientDep,
) -> ApprovalResponse:
    org_id = await get_action_sheet_org_id(client=client, action_sheet_id=action_sheet_id)
    await require_org_role(
        client=client,
        org_id=org_id,
        user=user,
        allowed_roles=("admin",),
    )
    return await update_approval_status(
        client=write_client,
        action_sheet_id=action_sheet_id,
        recommendation_id=recommendation_id,
        status=request.status,
        user=user,
    )

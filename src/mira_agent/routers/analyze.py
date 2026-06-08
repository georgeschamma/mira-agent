from typing import Annotated

from fastapi import APIRouter, Depends

from mira_agent.dependencies import get_rls_client, get_write_client, require_org_role, require_user
from mira_agent.graph.graph import run_mira_analysis
from mira_agent.repositories.rls_client import RlsClient
from mira_agent.schemas.analyze import AnalyzeRequest, AnalyzeResponse
from mira_agent.schemas.auth import CurrentUser

router = APIRouter(prefix="/api", tags=["analyze"])

UserDep = Annotated[CurrentUser, Depends(require_user)]
RlsClientDep = Annotated[RlsClient, Depends(get_rls_client)]
WriteClientDep = Annotated[RlsClient, Depends(get_write_client)]


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze(
    request: AnalyzeRequest,
    user: UserDep,
    client: RlsClientDep,
    write_client: WriteClientDep,
) -> AnalyzeResponse:
    await require_org_role(
        client=client,
        org_id=request.org_id,
        user=user,
        allowed_roles=("analyst", "admin"),
    )
    return await run_mira_analysis(client=write_client, request=request, user=user)

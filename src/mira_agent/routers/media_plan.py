from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, UploadFile

from mira_agent.dependencies import get_rls_client, get_write_client, require_org_role, require_user
from mira_agent.exceptions import ApiError
from mira_agent.graph.graph import run_media_plan_analysis
from mira_agent.repositories.rls_client import RlsClient
from mira_agent.schemas.auth import CurrentUser
from mira_agent.schemas.media_plan import MediaPlanGraphRequest, MediaPlanResponse

router = APIRouter(prefix="/api", tags=["media-plan"])
MAX_CSV_UPLOAD_BYTES = 2 * 1024 * 1024
UPLOAD_READ_CHUNK_BYTES = 64 * 1024

UserDep = Annotated[CurrentUser, Depends(require_user)]
RlsClientDep = Annotated[RlsClient, Depends(get_rls_client)]
WriteClientDep = Annotated[RlsClient, Depends(get_write_client)]


@router.post("/media-plan", response_model=MediaPlanResponse)
async def create_media_plan(
    user: UserDep,
    client: RlsClientDep,
    write_client: WriteClientDep,
    org_id: Annotated[str, Form()],
    brief: Annotated[str, Form()],
    crm_csv: Annotated[UploadFile | None, File()] = None,
    ga4_csv: Annotated[UploadFile | None, File()] = None,
) -> MediaPlanResponse:
    await require_org_role(
        client=client,
        org_id=org_id,
        user=user,
        allowed_roles=("analyst", "admin"),
    )
    if crm_csv is None:
        raise ApiError("MEDIA_PLAN_FILE_REQUIRED", "CRM CSV upload is required.", 400)
    if ga4_csv is None:
        raise ApiError("MEDIA_PLAN_FILE_REQUIRED", "GA4 CSV upload is required.", 400)

    request = MediaPlanGraphRequest(
        org_id=org_id,
        brief=brief,
        crm_csv_text=await _read_upload_text(crm_csv, "CRM"),
        crm_filename=crm_csv.filename or "crm.csv",
        ga4_csv_text=await _read_upload_text(ga4_csv, "GA4"),
        ga4_filename=ga4_csv.filename or "ga4.csv",
    )
    return await run_media_plan_analysis(client=write_client, request=request, user=user)


async def _read_upload_text(upload: UploadFile, label: str) -> str:
    chunks: list[bytes] = []
    total_size = 0
    while chunk := await upload.read(UPLOAD_READ_CHUNK_BYTES):
        total_size += len(chunk)
        if total_size > MAX_CSV_UPLOAD_BYTES:
            raise ApiError(
                "MEDIA_PLAN_FILE_TOO_LARGE",
                f"{label} CSV must be 2 MB or smaller.",
                413,
            )
        chunks.append(chunk)

    payload = b"".join(chunks)
    try:
        return payload.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ApiError(
            "CSV_DECODE_FAILED",
            f"{label} CSV must be UTF-8 encoded.",
            400,
        ) from exc

from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from mira_agent.exceptions import ApiError
from mira_agent.repositories.rls_client import PostgrestError, RlsClient
from mira_agent.schemas.media_plan import DocumentStatus

DOCUMENT_RECOMMENDATION_ID = "document"


@dataclass(frozen=True, slots=True)
class MediaPlanDocumentIds:
    action_sheet_id: str
    approval_id: str | None


async def save_media_plan_document(
    *,
    client: RlsClient,
    campaign_id: str,
    run_id: str,
    document_markdown: str,
    document_metadata: dict[str, object],
    model_used: str,
    processing_ms: int,
    approval_required: bool = True,
) -> MediaPlanDocumentIds:
    action_sheet_id = str(uuid4())
    approval_id = str(uuid4()) if approval_required else None
    document_status: DocumentStatus = "pending" if approval_required else "draft"

    try:
        await client.insert(
            "action_sheets",
            {
                "id": action_sheet_id,
                "campaign_id": campaign_id,
                "run_id": run_id,
                "recommendations": [],
                "model_used": model_used,
                "processing_ms": processing_ms,
                "document_markdown": document_markdown,
                "document_metadata": document_metadata,
                "document_status": document_status,
            },
        )
        if approval_id is not None:
            await client.insert(
                "action_sheet_approvals",
                {
                    "id": approval_id,
                    "action_sheet_id": action_sheet_id,
                    "recommendation_id": DOCUMENT_RECOMMENDATION_ID,
                    "status": "pending",
                },
            )
    except PostgrestError as exc:
        raise ApiError(
            "DB_WRITE_FAILED",
            "Could not save the media-plan document through RLS.",
            500,
        ) from exc

    return MediaPlanDocumentIds(action_sheet_id=action_sheet_id, approval_id=approval_id)

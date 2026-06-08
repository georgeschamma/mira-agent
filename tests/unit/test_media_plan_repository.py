from typing import Any

import pytest

from mira_agent.repositories.media_plans import (
    DOCUMENT_RECOMMENDATION_ID,
    save_media_plan_document,
)


class FakeRlsClient:
    def __init__(self) -> None:
        self.inserts: list[tuple[str, dict[str, Any]]] = []

    async def insert(self, table: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
        self.inserts.append((table, payload))
        return [payload]


@pytest.mark.asyncio
async def test_save_media_plan_document_writes_sheet_and_document_approval() -> None:
    client = FakeRlsClient()

    ids = await save_media_plan_document(
        client=client,  # type: ignore[arg-type]
        campaign_id="campaign_1",
        run_id="run_1",
        document_markdown="# Media Plan",
        document_metadata={"source_count": 3},
        model_used="test-model",
        processing_ms=123,
    )

    sheet = [payload for table, payload in client.inserts if table == "action_sheets"][0]
    approval = [
        payload for table, payload in client.inserts if table == "action_sheet_approvals"
    ][0]

    assert ids.action_sheet_id == sheet["id"]
    assert ids.approval_id == approval["id"]
    assert sheet["recommendations"] == []
    assert sheet["document_markdown"] == "# Media Plan"
    assert sheet["document_status"] == "pending"
    assert approval["recommendation_id"] == DOCUMENT_RECOMMENDATION_ID

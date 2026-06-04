from typing import Any

import pytest

from mira_agent.repositories.approvals import update_approval_status
from mira_agent.schemas.auth import CurrentUser


class FakeWriteClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def rpc(self, function: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
        self.calls.append((function, payload))
        return [
            {
                "action_sheet_id": payload["target_action_sheet_id"],
                "recommendation_id": payload["target_recommendation_id"],
                "status": payload["target_status"],
            }
        ]


@pytest.mark.asyncio
async def test_update_document_approval_calls_atomic_rpc() -> None:
    client = FakeWriteClient()

    result = await update_approval_status(
        client=client,  # type: ignore[arg-type]
        action_sheet_id="sheet_1",
        recommendation_id="document",
        status="approved",
        user=CurrentUser(id="admin_1", token="jwt"),
    )

    assert result.status == "approved"
    assert client.calls[0][0] == "update_action_sheet_approval"
    assert client.calls[0][1]["target_action_sheet_id"] == "sheet_1"

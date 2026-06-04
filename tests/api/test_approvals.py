from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mira_agent.dependencies import get_rls_client, get_write_client, require_user
from mira_agent.main import app
from mira_agent.schemas.auth import CurrentUser


class FakeReadClient:
    async def select(
        self,
        table: str,
        *,
        select: str = "*",
        filters: dict[str, str] | None = None,
        limit: int | None = None,
        order: str | None = None,
    ) -> list[dict[str, Any]]:
        if table == "action_sheets":
            return [{"campaigns": {"org_id": "org_1"}}]
        if table == "organization_members":
            return [{"role": "admin"}]
        return []


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


@pytest.fixture(autouse=True)
def clear_dependency_overrides() -> Iterator[None]:
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()


def test_admin_approval_uses_backend_write_client() -> None:
    write_client = FakeWriteClient()
    app.dependency_overrides[require_user] = lambda: CurrentUser(id="admin_1", token="jwt")
    app.dependency_overrides[get_rls_client] = lambda: FakeReadClient()
    app.dependency_overrides[get_write_client] = lambda: write_client
    client = TestClient(app)

    response = client.post(
        "/api/action-sheets/sheet_1/approvals/document",
        json={"status": "approved"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "approved"
    assert write_client.calls[0][0] == "update_action_sheet_approval"
    assert write_client.calls[0][1]["target_recommendation_id"] == "document"

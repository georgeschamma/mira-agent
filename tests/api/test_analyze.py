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
        if table == "organization_members":
            return [{"role": "analyst"}]
        return []


@pytest.fixture(autouse=True)
def clear_dependency_overrides() -> Iterator[None]:
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()


def test_analyze_uses_backend_write_client(monkeypatch: pytest.MonkeyPatch) -> None:
    write_client = object()
    app.dependency_overrides[require_user] = lambda: CurrentUser(id="user_1", token="jwt")
    app.dependency_overrides[get_rls_client] = lambda: FakeReadClient()
    app.dependency_overrides[get_write_client] = lambda: write_client

    async def fake_run_mira_analysis(*, client, request, user):
        assert client is write_client
        return {
            "campaign_id": "campaign_1",
            "run_id": "run_1",
            "action_sheet_id": "sheet_1",
            "approval_id": None,
            "recommendations": [],
        }

    monkeypatch.setattr("mira_agent.routers.analyze.run_mira_analysis", fake_run_mira_analysis)
    client = TestClient(app)

    response = client.post(
        "/api/analyze",
        json={
            "org_id": "11111111-1111-4111-8111-111111111111",
            "product": "MIRA",
            "audience": "B2B marketers",
            "channels": ["linkedin"],
            "budget": 1000,
            "goal": "book demos",
        },
    )

    assert response.status_code == 200
    assert response.json()["campaign_id"] == "campaign_1"

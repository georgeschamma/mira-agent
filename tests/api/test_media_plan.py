from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mira_agent.dependencies import get_rls_client, require_user
from mira_agent.main import app
from mira_agent.schemas.auth import CurrentUser


class FakeRlsClient:
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


async def fake_user() -> CurrentUser:
    return CurrentUser(id="user_1", email="analyst@mira.local", token="jwt")


def _files() -> dict[str, tuple[str, str, str]]:
    return {
        "crm_csv": (
            "crm.csv",
            "email,company,lifecycle_stage\na@example.com,Acme,lead\n",
            "text/csv",
        ),
        "ga4_csv": (
            "ga4.csv",
            "date,source,medium,channel,cost,conversions,total_revenue\n"
            "2026-05-01,google,cpc,Paid Search,100,4,400\n",
            "text/csv",
        ),
    }


def _data() -> dict[str, str]:
    return {
        "org_id": "11111111-1111-4111-8111-111111111111",
        "brief": "Product: MIRA\nAudience: B2B marketers\nBudget: 1000\nGoal: book demos",
    }


def test_media_plan_requires_bearer_token() -> None:
    client = TestClient(app)

    response = client.post("/api/media-plan", data=_data(), files=_files())

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_REQUIRED"


def test_media_plan_missing_csv_returns_stable_error() -> None:
    app.dependency_overrides[require_user] = fake_user
    app.dependency_overrides[get_rls_client] = lambda: FakeRlsClient()
    client = TestClient(app)

    response = client.post("/api/media-plan", data=_data())

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "MEDIA_PLAN_FILE_REQUIRED"


def test_media_plan_rejects_oversized_csv(monkeypatch: pytest.MonkeyPatch) -> None:
    app.dependency_overrides[require_user] = fake_user
    app.dependency_overrides[get_rls_client] = lambda: FakeRlsClient()
    monkeypatch.setattr("mira_agent.routers.media_plan.MAX_CSV_UPLOAD_BYTES", 16)
    client = TestClient(app)

    response = client.post("/api/media-plan", data=_data(), files=_files())

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "MEDIA_PLAN_FILE_TOO_LARGE"


def test_media_plan_valid_multipart_returns_response_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    app.dependency_overrides[require_user] = fake_user
    app.dependency_overrides[get_rls_client] = lambda: FakeRlsClient()

    async def fake_run_media_plan_analysis(*, client, request, user):
        assert request.crm_filename == "crm.csv"
        assert request.ga4_filename == "ga4.csv"
        return {
            "campaign_id": "campaign_1",
            "run_id": "run_1",
            "action_sheet_id": "sheet_1",
            "approval_id": "approval_1",
            "document_markdown": "# Media Plan",
            "document_status": "pending",
            "approvals": ["pending"],
            "crm_file": {"filename": "crm.csv", "row_count": 1, "warnings": []},
            "ga4_file": {"filename": "ga4.csv", "row_count": 1, "warnings": []},
            "audience_segments": [],
            "channel_summaries": [],
            "allocations": [],
        }

    monkeypatch.setattr(
        "mira_agent.routers.media_plan.run_media_plan_analysis",
        fake_run_media_plan_analysis,
    )
    client = TestClient(app)

    response = client.post("/api/media-plan", data=_data(), files=_files())

    assert response.status_code == 200
    body = response.json()
    assert body["action_sheet_id"] == "sheet_1"
    assert body["document_markdown"] == "# Media Plan"

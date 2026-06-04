from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mira_agent.dependencies import get_rls_client, require_user
from mira_agent.main import app
from mira_agent.schemas.auth import CurrentUser


class FakeRlsClient:
    def __init__(self, rows_by_table: dict[str, list[dict[str, Any]]]) -> None:
        self.rows_by_table = rows_by_table

    async def select(
        self,
        table: str,
        *,
        select: str = "*",
        filters: dict[str, str] | None = None,
        limit: int | None = None,
        order: str | None = None,
    ) -> list[dict[str, Any]]:
        return self.rows_by_table.get(table, [])


@pytest.fixture(autouse=True)
def clear_dependency_overrides() -> Iterator[None]:
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()


def _brief() -> dict[str, Any]:
    return {
        "org_id": "11111111-1111-4111-8111-111111111111",
        "product": "MIRA",
        "audience": "B2B marketers",
        "channels": ["linkedin"],
        "budget": 1000,
        "goal": "book demos",
    }


def _recommendation() -> dict[str, Any]:
    return {
        "id": "rec_linkedin",
        "domain": "content",
        "finding": "Use proof-led LinkedIn content.",
        "source": "https://example.com/source",
        "effort": "low",
        "impact": "high",
        "action": "Publish a sourced proof post.",
        "needs_approval": True,
    }


async def fake_user() -> CurrentUser:
    return CurrentUser(id="user_1", email="analyst@mira.local", token="jwt")


def override_client(rows_by_table: dict[str, list[dict[str, Any]]]) -> None:
    app.dependency_overrides[require_user] = fake_user
    app.dependency_overrides[get_rls_client] = lambda: FakeRlsClient(rows_by_table)


def test_action_sheet_report_requires_bearer_token() -> None:
    client = TestClient(app)

    response = client.get("/api/action-sheets/sheet_1")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_REQUIRED"


def test_runtime_config_returns_only_browser_safe_shape() -> None:
    client = TestClient(app)

    response = client.get("/api/config")

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {
        "app_name",
        "app_version",
        "supabase_url",
        "supabase_anon_key",
    }


def test_action_sheet_report_returns_typed_shape() -> None:
    override_client(
        {
            "action_sheets": [
                {
                    "id": "sheet_1",
                    "campaign_id": "campaign_1",
                    "run_id": "run_1",
                    "recommendations": [_recommendation()],
                    "model_used": "test-model",
                    "processing_ms": 1234,
                    "created_at": "2026-06-02T10:00:00Z",
                    "campaigns": {
                        "org_id": "11111111-1111-4111-8111-111111111111",
                        "brief": _brief(),
                    },
                }
            ],
            "action_sheet_approvals": [
                {
                    "recommendation_id": "rec_linkedin",
                    "status": "pending",
                    "approved_by": None,
                    "approved_at": None,
                    "created_at": "2026-06-02T10:01:00Z",
                }
            ],
        }
    )
    client = TestClient(app)

    response = client.get("/api/action-sheets/sheet_1")

    assert response.status_code == 200
    body = response.json()
    assert body["action_sheet_id"] == "sheet_1"
    assert body["brief"]["product"] == "MIRA"
    assert body["recommendations"][0]["id"] == "rec_linkedin"
    assert body["approvals"][0]["status"] == "pending"


def test_audit_trace_returns_rows_ordered_by_step_index() -> None:
    override_client(
        {
            "audit_log": [
                {
                    "id": "audit_2",
                    "campaign_id": "campaign_1",
                    "run_id": "run_1",
                    "step_index": 2,
                    "node": "content",
                    "summary": "Created recommendations.",
                    "source": "https://example.com/source",
                    "confidence": "high",
                    "pii_accessed": False,
                    "model_used": "test-model",
                    "created_at": "2026-06-02T10:02:00Z",
                },
                {
                    "id": "audit_0",
                    "campaign_id": "campaign_1",
                    "run_id": "run_1",
                    "step_index": 0,
                    "node": "router",
                    "summary": "Created campaign run.",
                    "source": "brief:product",
                    "confidence": "high",
                    "pii_accessed": False,
                    "model_used": "router",
                    "created_at": "2026-06-02T10:00:00Z",
                },
            ]
        }
    )
    client = TestClient(app)

    response = client.get("/api/runs/run_1/audit")

    assert response.status_code == 200
    body = response.json()
    assert body["run_id"] == "run_1"
    assert [row["node"] for row in body["rows"]] == ["router", "content"]


def test_missing_report_and_audit_return_stable_404_codes() -> None:
    override_client({"action_sheets": [], "audit_log": []})
    client = TestClient(app)

    report_response = client.get("/api/action-sheets/missing")
    audit_response = client.get("/api/runs/missing/audit")

    assert report_response.status_code == 404
    assert report_response.json()["error"]["code"] == "ACTION_SHEET_NOT_FOUND"
    assert audit_response.status_code == 404
    assert audit_response.json()["error"]["code"] == "AUDIT_TRACE_NOT_FOUND"

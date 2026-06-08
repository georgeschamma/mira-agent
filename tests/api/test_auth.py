from fastapi.testclient import TestClient

from mira_agent.dependencies import get_rls_client, get_write_client, require_user
from mira_agent.main import app
from mira_agent.schemas.auth import CurrentUser

VALID_ANALYZE_PAYLOAD = {
    "org_id": "11111111-1111-4111-8111-111111111111",
    "product": "MIRA",
    "audience": "B2B marketers",
    "channels": ["linkedin"],
    "budget": 1000,
    "goal": "book demos",
}


def test_analyze_requires_bearer_token() -> None:
    client = TestClient(app)

    response = client.post("/api/analyze", json=VALID_ANALYZE_PAYLOAD)

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_REQUIRED"


def test_analyze_rejects_invalid_bearer_token() -> None:
    client = TestClient(app)

    response = client.post(
        "/api/analyze",
        headers={"Authorization": "Bearer invalid-token"},
        json=VALID_ANALYZE_PAYLOAD,
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_INVALID"


def test_analyze_validation_error_uses_stable_envelope() -> None:
    app.dependency_overrides[require_user] = lambda: CurrentUser(id="user_1", token="jwt")
    app.dependency_overrides[get_rls_client] = lambda: object()
    app.dependency_overrides[get_write_client] = lambda: object()
    client = TestClient(app)

    response = client.post("/api/analyze", json={})

    app.dependency_overrides.clear()
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "REQUEST_VALIDATION_FAILED"
    assert response.json()["error"]["request_id"].startswith("req_")

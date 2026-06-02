from fastapi.testclient import TestClient

from mira_agent.main import app

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


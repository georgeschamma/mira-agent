from fastapi.testclient import TestClient

from mira_agent.main import app


def test_health_returns_healthy() -> None:
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_db_health_returns_status_shape() -> None:
    client = TestClient(app)

    response = client.get("/health/db")

    assert response.status_code == 200
    assert response.json()["status"] in {"healthy", "unhealthy"}


from fastapi.testclient import TestClient

from app.main import app


def test_liveness_contract() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/health/live")

    assert response.status_code == 200
    assert response.json() == {
        "name": "文渊 API",
        "environment": "development",
        "status": "ok",
        "version": "0.1.0",
        "services": {"api": "up"},
    }
    assert response.headers["X-Request-ID"]

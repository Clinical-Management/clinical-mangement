from fastapi.testclient import TestClient

from app.main import app


def test_health():
    # No `with` block: lifespan (Mongo connection) is not started
    client = TestClient(app)
    assert client.get("/health").json() == {"status": "ok"}


def test_protected_route_requires_auth():
    client = TestClient(app)
    assert client.get("/api/v1/auth/me").status_code == 401

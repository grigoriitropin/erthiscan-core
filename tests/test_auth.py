from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_auth_google_no_token():
    resp = client.post("/auth/google", json={})
    assert resp.status_code == 422


def test_auth_refresh_no_token():
    resp = client.post("/auth/refresh", json={})
    assert resp.status_code == 422

# INFRASTRUCTURE TESTS: Verifies liveness and observability.
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    """LIVENESS TEST: Verifies that the FastAPI process is running and responding."""
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_metrics():
    """OBSERVABILITY TEST: Ensures that the Prometheus metrics endpoint is exposed."""
    resp = client.get("/metrics")
    assert resp.status_code == 200

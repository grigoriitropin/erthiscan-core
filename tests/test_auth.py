import time
import uuid

import jwt
import pytest
from fastapi.testclient import TestClient

from app.api.auth import _make_access_token
from app.api.deps import _decode
from app.config import get_settings
from app.main import app

client = TestClient(app)
settings = get_settings()


def test_auth_google_missing_token():
    resp = client.post("/auth/google", json={})
    assert resp.status_code == 422


def test_auth_refresh_missing_token():
    resp = client.post("/auth/refresh", json={})
    assert resp.status_code == 422


def test_access_token_roundtrip_contains_all_required_claims():
    token = _make_access_token(user_id=42)
    payload = _decode(token)
    assert payload["user_id"] == 42
    for claim in ("iss", "aud", "iat", "nbf", "exp", "jti"):
        assert claim in payload, f"missing claim {claim}"
    assert payload["iss"] == settings.jwt_issuer
    assert payload["aud"] == settings.jwt_audience


def test_token_with_wrong_algorithm_rejected():
    # "none" alg attack — must be rejected by algorithm whitelist.
    now = int(time.time())
    token = jwt.encode(
        {
            "user_id": 1,
            "jti": str(uuid.uuid4()),
            "iss": settings.jwt_issuer,
            "aud": settings.jwt_audience,
            "iat": now,
            "nbf": now,
            "exp": now + 60,
        },
        key="",
        algorithm="none",
    )
    with pytest.raises(jwt.InvalidTokenError):
        _decode(token)


def test_token_with_wrong_issuer_rejected():
    now = int(time.time())
    token = jwt.encode(
        {
            "user_id": 1,
            "jti": str(uuid.uuid4()),
            "iss": "attacker",
            "aud": settings.jwt_audience,
            "iat": now,
            "nbf": now,
            "exp": now + 60,
        },
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
    with pytest.raises(jwt.InvalidIssuerError):
        _decode(token)


def test_token_with_wrong_audience_rejected():
    now = int(time.time())
    token = jwt.encode(
        {
            "user_id": 1,
            "jti": str(uuid.uuid4()),
            "iss": settings.jwt_issuer,
            "aud": "some-other-client",
            "iat": now,
            "nbf": now,
            "exp": now + 60,
        },
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
    with pytest.raises(jwt.InvalidAudienceError):
        _decode(token)


def test_token_missing_jti_rejected():
    now = int(time.time())
    token = jwt.encode(
        {
            "user_id": 1,
            "iss": settings.jwt_issuer,
            "aud": settings.jwt_audience,
            "iat": now,
            "nbf": now,
            "exp": now + 60,
        },
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
    with pytest.raises(jwt.MissingRequiredClaimError):
        _decode(token)


def test_expired_token_rejected():
    now = int(time.time())
    token = jwt.encode(
        {
            "user_id": 1,
            "jti": str(uuid.uuid4()),
            "iss": settings.jwt_issuer,
            "aud": settings.jwt_audience,
            "iat": now - 3600,
            "nbf": now - 3600,
            "exp": now - 60,
        },
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
    with pytest.raises(jwt.ExpiredSignatureError):
        _decode(token)


def test_nbf_in_future_rejected():
    now = int(time.time())
    token = jwt.encode(
        {
            "user_id": 1,
            "jti": str(uuid.uuid4()),
            "iss": settings.jwt_issuer,
            "aud": settings.jwt_audience,
            "iat": now,
            "nbf": now + 3600,
            "exp": now + 7200,
        },
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
    with pytest.raises(jwt.ImmatureSignatureError):
        _decode(token)


def test_unauthorized_endpoint_without_token():
    resp = client.get("/reports/me")
    assert resp.status_code == 401


def test_unauthorized_endpoint_with_garbage_token():
    resp = client.get("/reports/me", headers={"Authorization": "Bearer not.a.jwt"})
    assert resp.status_code == 401

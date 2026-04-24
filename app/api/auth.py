import asyncio
import secrets
import time
import uuid
from datetime import UTC, datetime, timedelta

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2 import id_token
from pydantic import BaseModel
from sqlalchemy import delete, select

from app.api.deps import bearer_scheme
from app.cache import blacklist_token
from app.config import get_settings
from app.models.database import WriteSession
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.rate_limit import limiter

router = APIRouter(prefix="/auth", tags=["auth"])

_settings = get_settings()

# Single Google Request instance reused across verify calls
_google_request = GoogleRequest()


class GoogleAuthRequest(BaseModel):
    token: str


class AuthResponse(BaseModel):
    access_token: str
    refresh_token: str
    user_id: int
    username: str


class RefreshRequest(BaseModel):
    refresh_token: str


def _make_access_token(user_id: int) -> str:
    now = int(time.time())
    return jwt.encode(
        {
            "user_id": user_id,
            "jti": str(uuid.uuid4()),
            "iss": _settings.jwt_issuer,
            "aud": _settings.jwt_audience,
            "iat": now,
            "nbf": now,
            "exp": now + _settings.jwt_expiry_seconds,
        },
        _settings.jwt_secret,
        algorithm=_settings.jwt_algorithm,
    )


@router.post("/google", response_model=AuthResponse)
@limiter.limit(_settings.rate_limit_auth)
async def auth_google(request: Request, payload: GoogleAuthRequest):
    try:
        idinfo = await asyncio.to_thread(
            id_token.verify_oauth2_token,
            payload.token,
            _google_request,
            _settings.google_web_client_id,
        )
    except ValueError:
        raise HTTPException(status_code=401, detail="invalid google token") from None

    # Defence-in-depth: re-check issuer (google-auth already does, but be explicit)
    if idinfo.get("iss") not in ("accounts.google.com", "https://accounts.google.com"):
        raise HTTPException(status_code=401, detail="invalid google issuer")

    google_id = idinfo["sub"]
    username = idinfo.get("name", idinfo.get("email", "user"))

    if WriteSession is None:
        raise HTTPException(status_code=500, detail="database not configured")

    async with WriteSession() as session:
        result = await session.execute(
            select(User).where(User.google_id == google_id)
        )
        user = result.scalar_one_or_none()

        if user is None:
            user = User(google_id=google_id, username=username)
            session.add(user)
            await session.commit()
            await session.refresh(user)

        refresh_token_str = secrets.token_urlsafe(64)
        expires_at = datetime.now(UTC) + timedelta(days=_settings.refresh_token_ttl_days)
        session.add(RefreshToken(user_id=user.id, token=refresh_token_str, expires_at=expires_at))
        await session.commit()

    access_token = _make_access_token(user.id)

    return AuthResponse(
        access_token=access_token,
        refresh_token=refresh_token_str,
        user_id=user.id,
        username=user.username,
    )


class RefreshResponse(BaseModel):
    access_token: str
    refresh_token: str


@router.post("/refresh", response_model=RefreshResponse)
@limiter.limit(_settings.rate_limit_auth)
async def refresh(request: Request, payload: RefreshRequest):
    if WriteSession is None:
        raise HTTPException(status_code=500, detail="database not configured")

    async with WriteSession() as session:
        result = await session.execute(
            select(RefreshToken).where(RefreshToken.token == payload.refresh_token).with_for_update()
        )
        rt = result.scalar_one_or_none()
        if rt is None:
            raise HTTPException(status_code=401, detail="invalid refresh token")

        if rt.expires_at is not None and rt.expires_at < datetime.now(UTC):
            await session.delete(rt)
            await session.commit()
            raise HTTPException(status_code=401, detail="refresh token expired")

        user_id = rt.user_id

        # Rotate: delete old, create new
        await session.delete(rt)
        new_refresh = secrets.token_urlsafe(64)
        expires_at = datetime.now(UTC) + timedelta(days=_settings.refresh_token_ttl_days)
        session.add(RefreshToken(user_id=user_id, token=new_refresh, expires_at=expires_at))
        await session.commit()

    return RefreshResponse(
        access_token=_make_access_token(user_id),
        refresh_token=new_refresh,
    )


@router.post("/logout")
async def logout(credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)):
    try:
        payload = jwt.decode(
            credentials.credentials,
            _settings.jwt_secret,
            algorithms=[_settings.jwt_algorithm],
            audience=_settings.jwt_audience,
            issuer=_settings.jwt_issuer,
            options={"require": ["exp", "jti", "user_id"]},
        )
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="invalid token") from None

    jti = payload.get("jti")
    if jti:
        ttl = int(payload["exp"] - time.time())
        if ttl > 0:
            await blacklist_token(jti, ttl)

    user_id = payload.get("user_id")
    if user_id and WriteSession is not None:
        async with WriteSession() as session:
            await session.execute(
                delete(RefreshToken).where(RefreshToken.user_id == user_id)
            )
            await session.commit()

    return {"status": "ok"}

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

# ROUTER CONFIGURATION: Defines the '/auth' namespace for all authentication-related endpoints.
# The 'tags' parameter groups these routes in the automatically generated Swagger/OpenAPI documentation.
router = APIRouter(prefix="/auth", tags=["auth"])

_settings = get_settings()

# GOOGLE HTTP CLIENT: We reuse a single GoogleRequest instance to optimize performance.
# This instance handles the low-level HTTP calls required to verify ID tokens against Google's servers.
_google_request = GoogleRequest()


class GoogleAuthRequest(BaseModel):
    """Input schema for Google authentication, expecting a raw ID Token from the frontend."""

    token: str


class AuthResponse(BaseModel):
    """Unified response schema containing session tokens and essential user identity data."""

    access_token: str
    refresh_token: str
    user_id: int
    username: str


class RefreshRequest(BaseModel):
    """Input schema for session renewal using a previously issued refresh token."""

    refresh_token: str


def _make_access_token(user_id: int) -> str:
    """
    JWT FACTORY: Generates a signed, short-lived Access Token.

    CLAIMS EXPLAINED:
    - user_id: The primary identifier for the owner of the token.
    - jti (JWT ID): A unique UUID for this specific token, allowing it to be blacklisted.
    - iss/aud: Issuer and Audience claims to prevent token misuse across different services.
    - iat (Issued At): The exact time the token was created.
    - nbf (Not Before): Prevents the token from being used before it was issued.
    - exp (Expiry): Time-bound security limit (usually 1 hour).
    """
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
    """
    GOOGLE AUTHENTICATION FLOW:
    1. VALIDATION: The Google ID Token is verified. We use 'asyncio.to_thread'
       because the 'id_token.verify_oauth2_token' function is synchronous and blocking;
       running it directly would freeze the entire FastAPI event loop.
    2. IDENTITY: Extracts 'sub' (Google's unique user ID) and profile info.
    3. PERSISTENCE: Performs an 'Upsert' — finds the existing user or creates a new one in the DB.
    4. SESSION: Generates a cryptographically strong Refresh Token using 'secrets.token_urlsafe'
       and records it in the database with a 30-day expiry.
    """
    try:
        idinfo = await asyncio.to_thread(
            id_token.verify_oauth2_token,
            payload.token,
            _google_request,
            _settings.google_web_client_id,
        )
    except ValueError:
        raise HTTPException(status_code=401, detail="invalid google token") from None

    # DEFENSE-IN-DEPTH: Explicitly verify the issuer to prevent 'token substitution' attacks.
    if idinfo.get("iss") not in ("accounts.google.com", "https://accounts.google.com"):
        raise HTTPException(status_code=401, detail="invalid google issuer")

    google_id = idinfo["sub"]
    username = idinfo.get("name", idinfo.get("email", "user"))

    if WriteSession is None:
        raise HTTPException(status_code=500, detail="database not configured")

    async with WriteSession() as session:
        # USER LOOKUP: Fetch user by their immutable Google ID.
        result = await session.execute(select(User).where(User.google_id == google_id))
        user = result.scalar_one_or_none()

        if user is None:
            # ONBOARDING: Create new user entry if this is their first login.
            user = User(google_id=google_id, username=username)
            session.add(user)
            await session.commit()
            await session.refresh(user)

        # TOKEN GENERATION: Create a long-lived, high-entropy refresh token.
        refresh_token_str = secrets.token_urlsafe(64)
        expires_at = datetime.now(UTC) + timedelta(days=_settings.refresh_token_ttl_days)
        session.add(RefreshToken(user_id=user.id, token=refresh_token_str, expires_at=expires_at))
        await session.commit()

    # ISSUE SESSION: Return the first Access Token and the new Refresh Token.
    access_token = _make_access_token(user.id)

    return AuthResponse(
        access_token=access_token,
        refresh_token=refresh_token_str,
        user_id=user.id,
        username=user.username,
    )


class RefreshResponse(BaseModel):
    """Schema for renewed credentials."""

    access_token: str
    refresh_token: str


@router.post("/refresh", response_model=RefreshResponse)
@limiter.limit(_settings.rate_limit_auth)
async def refresh(request: Request, payload: RefreshRequest):
    """
    TOKEN ROTATION FLOW:
    This endpoint implements a secure 'single-use' refresh token pattern.
    1. LOCKING: Uses 'with_for_update()' to perform a row-level lock on the token entry.
       This prevents race conditions where a token might be refreshed twice simultaneously.
    2. VERIFICATION: Checks if the token exists and hasn't expired.
    3. ROTATION: The old token is DELETED and a completely new one is issued.
       If a stolen token is reused, the rotation chain breaks, signaling a potential breach.
    """
    if WriteSession is None:
        raise HTTPException(status_code=500, detail="database not configured")

    async with WriteSession() as session:
        # Atomic fetch-and-lock of the refresh token.
        result = await session.execute(
            select(RefreshToken)
            .where(RefreshToken.token == payload.refresh_token)
            .with_for_update()
        )
        rt = result.scalar_one_or_none()
        if rt is None:
            raise HTTPException(status_code=401, detail="invalid refresh token")

        # EXPIRY ENFORCEMENT: Clean up the expired token and deny access.
        if rt.expires_at is not None and rt.expires_at < datetime.now(UTC):
            await session.delete(rt)
            await session.commit()
            raise HTTPException(status_code=401, detail="refresh token expired")

        user_id = rt.user_id

        # EXECUTE ROTATION: Remove the used token from the database.
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
    """
    SECURE LOGOUT FLOW:
    Since JWTs are stateless, we use a hybrid approach to invalidate them:
    1. ACCESS TOKEN: The unique 'jti' of the token is extracted and stored in a Redis
       blacklist until its natural expiry time. The API middleware checks this list.
    2. REFRESH TOKENS: All persistent refresh tokens for the user are deleted from
       the database, effectively ending their session on all devices.
    """
    try:
        # DECODE: Verify the token signature and claims before processing logout.
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
        # REDIS BLACKLIST: Store the token ID for the remainder of its lifespan.
        ttl = int(payload["exp"] - time.time())
        if ttl > 0:
            await blacklist_token(jti, ttl)

    user_id = payload.get("user_id")
    if user_id and WriteSession is not None:
        async with WriteSession() as session:
            # PERSISTENT SESSION CLEARANCE: Nukes all refresh tokens for this user.
            await session.execute(delete(RefreshToken).where(RefreshToken.user_id == user_id))
            await session.commit()

    return {"status": "ok"}

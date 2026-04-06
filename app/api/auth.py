import asyncio
import os
import secrets
import time
import uuid
from functools import partial

import jwt
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2 import id_token
from pydantic import BaseModel
from sqlalchemy import select, delete

from app.cache import blacklist_token, is_token_blacklisted
from app.models.database import WriteSession
from app.models.refresh_token import RefreshToken
from app.models.user import User

router = APIRouter(prefix="/auth", tags=["auth"])

GOOGLE_WEB_CLIENT_ID = os.environ.get("GOOGLE_WEB_CLIENT_ID", "")
JWT_SECRET = os.environ.get("JWT_SECRET", "")
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_SECONDS = 3600  # 1 hour


class GoogleAuthRequest(BaseModel):
    token: str


class AuthResponse(BaseModel):
    access_token: str
    refresh_token: str
    user_id: int
    username: str


class RefreshRequest(BaseModel):
    refresh_token: str


class RefreshResponse(BaseModel):
    access_token: str


def _make_access_token(user_id: int) -> str:
    return jwt.encode(
        {
            "user_id": user_id,
            "jti": str(uuid.uuid4()),
            "exp": int(time.time()) + JWT_EXPIRY_SECONDS,
        },
        JWT_SECRET,
        algorithm=JWT_ALGORITHM,
    )


@router.post("/google", response_model=AuthResponse)
async def auth_google(payload: GoogleAuthRequest):
    if not GOOGLE_WEB_CLIENT_ID or not JWT_SECRET:
        raise HTTPException(status_code=500, detail="auth not configured")

    try:
        loop = asyncio.get_event_loop()
        idinfo = await loop.run_in_executor(
            None,
            partial(id_token.verify_oauth2_token, payload.token, GoogleRequest(), GOOGLE_WEB_CLIENT_ID),
        )
    except ValueError:
        raise HTTPException(status_code=401, detail="invalid google token")

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

        # Create refresh token
        refresh_token_str = secrets.token_urlsafe(64)
        session.add(RefreshToken(user_id=user.id, token=refresh_token_str))
        await session.commit()

    access_token = _make_access_token(user.id)

    return AuthResponse(
        access_token=access_token,
        refresh_token=refresh_token_str,
        user_id=user.id,
        username=user.username,
    )


@router.post("/refresh", response_model=RefreshResponse)
async def refresh(payload: RefreshRequest):
    if WriteSession is None:
        raise HTTPException(status_code=500, detail="database not configured")

    async with WriteSession() as session:
        result = await session.execute(
            select(RefreshToken).where(RefreshToken.token == payload.refresh_token)
        )
        rt = result.scalar_one_or_none()
        if rt is None:
            raise HTTPException(status_code=401, detail="invalid refresh token")

        access_token = _make_access_token(rt.user_id)

    return RefreshResponse(access_token=access_token)


bearer_scheme = HTTPBearer()


@router.post("/logout")
async def logout(credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)):
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="invalid token")

    jti = payload.get("jti")
    if jti:
        ttl = int(payload["exp"] - time.time())
        if ttl > 0:
            await blacklist_token(jti, ttl)

    # Delete all refresh tokens for this user
    user_id = payload.get("user_id")
    if user_id and WriteSession is not None:
        async with WriteSession() as session:
            await session.execute(
                delete(RefreshToken).where(RefreshToken.user_id == user_id)
            )
            await session.commit()

    return {"status": "ok"}

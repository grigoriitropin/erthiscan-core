import asyncio
import os
import time
import uuid
from functools import partial

import jwt
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2 import id_token
from pydantic import BaseModel
from sqlalchemy import select

from app.cache import blacklist_token, is_token_blacklisted
from app.models.database import WriteSession
from app.models.user import User

router = APIRouter(prefix="/auth", tags=["auth"])

GOOGLE_WEB_CLIENT_ID = os.environ.get("GOOGLE_WEB_CLIENT_ID", "")
JWT_SECRET = os.environ.get("JWT_SECRET", "")
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_SECONDS = 86400  # 24 hours


class GoogleAuthRequest(BaseModel):
    token: str


class AuthResponse(BaseModel):
    access_token: str
    user_id: int
    username: str


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

    access_token = jwt.encode(
        {
            "user_id": user.id,
            "jti": str(uuid.uuid4()),
            "exp": int(time.time()) + JWT_EXPIRY_SECONDS,
        },
        JWT_SECRET,
        algorithm=JWT_ALGORITHM,
    )

    return AuthResponse(
        access_token=access_token,
        user_id=user.id,
        username=user.username,
    )


bearer_scheme = HTTPBearer()


@router.post("/logout")
async def logout(credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)):
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="invalid token")

    jti = payload.get("jti")
    if jti is None:
        return {"status": "ok"}

    ttl = int(payload["exp"] - time.time())
    if ttl > 0:
        await blacklist_token(jti, ttl)

    return {"status": "ok"}

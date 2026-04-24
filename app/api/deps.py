import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.cache import is_token_blacklisted
from app.config import get_settings

bearer_scheme = HTTPBearer()
optional_bearer = HTTPBearer(auto_error=False)

_JWT_DECODE_OPTIONS = {
    "require": ["exp", "iat", "nbf", "jti", "iss", "aud", "user_id"],
    "verify_signature": True,
    "verify_exp": True,
    "verify_nbf": True,
    "verify_iat": True,
    "verify_aud": True,
    "verify_iss": True,
}


def _decode(token: str) -> dict:
    settings = get_settings()
    return jwt.decode(
        token,
        settings.jwt_secret,
        algorithms=[settings.jwt_algorithm],
        audience=settings.jwt_audience,
        issuer=settings.jwt_issuer,
        options=_JWT_DECODE_OPTIONS,
    )


async def get_current_user_id(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> int:
    try:
        payload = _decode(credentials.credentials)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="invalid token")

    if await is_token_blacklisted(payload["jti"]):
        raise HTTPException(status_code=401, detail="token revoked")

    return int(payload["user_id"])


async def get_optional_user_id(
    credentials: HTTPAuthorizationCredentials | None = Depends(optional_bearer),
) -> int | None:
    if credentials is None:
        return None
    try:
        payload = _decode(credentials.credentials)
    except jwt.InvalidTokenError:
        return None

    if await is_token_blacklisted(payload["jti"]):
        return None

    return int(payload["user_id"])

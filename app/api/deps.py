import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.cache import is_token_blacklisted
from app.config import get_settings

# SECURITY SCHEMES: Define how FastAPI extracts the token from the Authorization header.
# bearer_scheme strictly requires a token (returns 401 if missing).
bearer_scheme = HTTPBearer()
# optional_bearer allows requests without a token, useful for endpoints that behave 
# differently for guests vs. logged-in users (like company details).
optional_bearer = HTTPBearer(auto_error=False)

# STRICT DECODING OPTIONS: Hardened configuration for the PyJWT library.
# We explicitly require and verify all critical claims to prevent token manipulation.
_JWT_DECODE_OPTIONS = {
    "require": ["exp", "iat", "nbf", "jti", "iss", "aud", "user_id"],
    "verify_signature": True,
    "verify_exp": True, # Expiration time
    "verify_nbf": True, # Not before time
    "verify_iat": True, # Issued at time
    "verify_aud": True, # Audience (must be for this specific app)
    "verify_iss": True, # Issuer (must be our core backend)
}


def _decode(token: str) -> dict:
    """
    INTERNAL HELPER: Decodes and cryptographically verifies the JWT.
    Uses the configuration settings loaded via Pydantic.
    """
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
    """
    FASTAPI DEPENDENCY: Enforces strict authentication.
    
    FLOW:
    1. Extracts the Bearer token from the request header.
    2. Decodes and verifies the token's cryptographic signature and claims.
    3. Checks the Redis blacklist to ensure the token hasn't been revoked (e.g., via logout).
    Returns the user_id integer if successful, or raises a 401 HTTPException.
    """
    try:
        payload = _decode(credentials.credentials)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="token expired") from None
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="invalid token") from None

    # STATELESS LOGOUT SUPPORT: Check if the token's unique ID (JTI) is in the Redis blacklist.
    if await is_token_blacklisted(payload["jti"]):
        raise HTTPException(status_code=401, detail="token revoked")

    return int(payload["user_id"])


async def get_optional_user_id(
    credentials: HTTPAuthorizationCredentials | None = Depends(optional_bearer),
) -> int | None:
    """
    FASTAPI DEPENDENCY: Optional authentication.
    
    Behaves exactly like get_current_user_id, but if the token is missing, 
    expired, or invalid, it gracefully returns None instead of raising an error.
    Used for endpoints that provide additional data (like user's own votes) if logged in.
    """
    if credentials is None:
        return None
    try:
        payload = _decode(credentials.credentials)
    except jwt.InvalidTokenError:
        return None

    # STATELESS LOGOUT SUPPORT: Silently fail to anonymous mode if the token is revoked.
    if await is_token_blacklisted(payload["jti"]):
        return None

    return int(payload["user_id"])

import logging
import os

# Patch slowapi's handler BEFORE middleware module-level code runs.
# Must be before get_settings() because middleware is imported by main.py earlier.
import slowapi.middleware as _mw
from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.responses import JSONResponse

from app.config import get_settings


def _safe_handler(request, exc):
    detail = getattr(exc, "detail", str(exc))
    return JSONResponse({"error": f"rate limit: {detail}"}, status_code=429)


_mw._rate_limit_exceeded_handler = _safe_handler


_settings = get_settings()

_log = logging.getLogger(__name__)

# Default to memory-based rate limiting. Use Redis when explicitly configured.
# On Kubernetes, set RATE_LIMITER_REDIS_URL=redis://redis.erthiscan:6379/0
_storage = os.getenv("RATE_LIMITER_REDIS_URL") or _settings.redis_url or "memory://"

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[_settings.rate_limit_default],
    storage_uri=_storage,
    strategy="moving-window",
)

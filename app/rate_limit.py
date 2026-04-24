from slowapi import Limiter
from slowapi.util import get_remote_address

from app.config import get_settings

_settings = get_settings()

import logging
import os

from starlette.responses import JSONResponse


def _safe_handler(request, exc):
    detail = getattr(exc, "detail", str(exc))
    return JSONResponse({"error": f"rate limit: {detail}"}, status_code=429)


# Patch slowapi's handler BEFORE middleware module-level code runs
import slowapi.middleware as _mw
_mw._rate_limit_exceeded_handler = _safe_handler


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

import logging
import os

from slowapi import Limiter
from starlette.requests import Request

from app.config import get_settings

_settings = get_settings()
_log = logging.getLogger(__name__)


def _client_ip(request: Request) -> str:
    """Return the real client IP when the app sits behind a reverse proxy.

    Traefik (and any sane ingress) sets X-Forwarded-For with the chain of
    hops; the left-most entry is the original client. We trust it because
    public traffic can only reach us via our own ingress — direct pod
    access would bypass rate limits anyway and is blocked at the network
    level. Falls back to X-Real-IP, then the socket peer, then a constant
    bucket so we never crash.
    """
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",", 1)[0].strip()
    real = request.headers.get("x-real-ip")
    if real:
        return real.strip()
    if request.client is not None:
        return request.client.host
    return "unknown"


# Default to memory-based rate limiting. Use Redis when explicitly configured.
# On Kubernetes, set RATE_LIMITER_REDIS_URL=redis://redis.erthiscan:6379/0
_storage = os.getenv("RATE_LIMITER_REDIS_URL") or _settings.redis_url or "memory://"

limiter = Limiter(
    key_func=_client_ip,
    default_limits=[_settings.rate_limit_default],
    storage_uri=_storage,
    strategy="moving-window",
)

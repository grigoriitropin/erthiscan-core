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


# --- RATE LIMITING STRATEGY ---
# We use the 'slowapi' library which integrates the 'limits' package with FastAPI.
# For high-availability on Kubernetes, we prefer 'redis://' storage so that 
# rate limits are shared across all pods. If Redis is unavailable, we fall 
# back to 'memory://' which limits each pod independently.
_storage = os.getenv("RATE_LIMITER_REDIS_URL") or _settings.redis_url or "memory://"

limiter = Limiter(
    key_func=_client_ip,
    # default_limits: Applied to every endpoint that doesn't have an explicit limit.
    default_limits=[_settings.rate_limit_default],
    storage_uri=_storage,
    # 'moving-window': The most precise strategy. It counts requests in a rolling time 
    # frame rather than fixed 1-minute blocks, preventing bursts at the turn of the minute.
    strategy="moving-window",
)

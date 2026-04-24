import logging
import sys
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from prometheus_fastapi_instrumentator import Instrumentator
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from sqlalchemy import text

from app.api.auth import router as auth_router
from app.api.barcode import router as barcode_router
from app.api.barcode import scan_router
from app.api.companies import router as companies_router
from app.api.reports import router as reports_router
from app.events import close_producer
from app.models.database import ReadSession, WriteSession
from app.rate_limit import limiter

structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logging.basicConfig(stream=sys.stdout, level=logging.INFO, force=True)
logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("app_starting")
    yield
    logger.info("app_shutting_down")
    await close_producer()
    from app.cache import _redis
    if _redis is not None:
        await _redis.aclose()


app = FastAPI(lifespan=lifespan)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    response = await call_next(request)
    structlog.contextvars.bind_contextvars(
        method=request.method,
        path=request.url.path,
        status=response.status_code,
    )
    logger.info("request_handled")
    return response


app.state.limiter = limiter


def _safe_rate_handler(request: Request, exc: Exception) -> JSONResponse:
    detail = getattr(exc, "detail", str(exc))
    return JSONResponse({"error": f"rate limit: {detail}"}, status_code=429)


app.add_exception_handler(RateLimitExceeded, _safe_rate_handler)
app.add_middleware(SlowAPIMiddleware)

Instrumentator().instrument(app).expose(app, tags=["metrics"])

app.include_router(auth_router)
app.include_router(barcode_router)
app.include_router(scan_router)
app.include_router(companies_router)
app.include_router(reports_router)


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.get("/db-health")
async def db_health():
    if WriteSession is None or ReadSession is None:
        raise HTTPException(status_code=500, detail="database is not configured")

    try:
        async with WriteSession() as session:
            await session.execute(text("SELECT 1"))
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"write: {e}") from e

    try:
        async with ReadSession() as session:
            await session.execute(text("SELECT 1"))
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"read: {e}") from e

    return {"database": "ok", "read": "ok"}

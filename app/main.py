from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from sqlalchemy import text

from app.api.auth import router as auth_router
from app.api.barcode import router as barcode_router, scan_router
from app.api.companies import router as companies_router
from app.cache import get_redis
from app.events import close_producer
from app.models.database import ReadSession, WriteSession


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await close_producer()
    from app.cache import _redis
    if _redis is not None:
        await _redis.aclose()


# create the fastapi application instance
app = FastAPI(lifespan=lifespan)

app.include_router(auth_router)
app.include_router(barcode_router)
app.include_router(scan_router)
app.include_router(companies_router)

# Define a simple health check endpoint
@app.get("/health")
def health_check():
    return {"status": "ok"}

@app.get("/db-health")
async def db_health():
    if WriteSession is None or ReadSession is None:
        raise HTTPException(status_code=500, detail="database is not configured")

    async with WriteSession() as session:
        await session.execute(text("SELECT 1"))
    async with ReadSession() as session:
        await session.execute(text("SELECT 1"))
    return {"database": "ok", "read": "ok"}

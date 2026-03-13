from fastapi import FastAPI, HTTPException
from sqlalchemy import text

from app.api.barcode import router as barcode_router, scan_router
from app.models.database import ReadSession, WriteSession

# create the fastapi application instance
app = FastAPI()

app.include_router(barcode_router)
app.include_router(scan_router)

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

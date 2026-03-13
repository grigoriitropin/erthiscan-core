from fastapi import FastAPI
from sqlalchemy import text
from app.models.database import ReadSession, WriteSession

# create the fastapi application instance
app = FastAPI()

# Define a simple health check endpoint
@app.get("/health")
def health_check():
    return {"status": "ok"}

@app.get("/db-health")
async def db_health():
    async with WriteSession() as session:
        await session.execute(text("SELECT 1"))
    async with ReadSession() as session:
        await session.execute(text("SELECT 1"))
    return {"database": "ok", "read": "ok"}

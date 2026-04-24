import os

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

# Database connection URL from environment variable
WRITE_URL = os.getenv("DB_WRITE_URL")
READ_URL = os.getenv("DB_READ_URL")


# Base class for all models
class Base(DeclarativeBase):
    pass

# Engine for writing (primary)
write_engine = create_async_engine(WRITE_URL, pool_pre_ping=True) if WRITE_URL else None

# Engine for reading (replicas)
read_engine = create_async_engine(READ_URL, pool_pre_ping=True) if READ_URL else None

# Session factories
WriteSession = (
    async_sessionmaker(write_engine, expire_on_commit=False)
    if write_engine is not None
    else None
)

ReadSession = (
    async_sessionmaker(read_engine, expire_on_commit=False)
    if read_engine is not None
    else None
)

import os

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

# CQRS ARCHITECTURE: We use separate URLs for reading and writing.
# In a CloudNativePG Kubernetes cluster, WRITE_URL points to the primary instance,
# while READ_URL points to a service that load-balances across all read-only replicas.
WRITE_URL = os.getenv("DB_WRITE_URL")
READ_URL = os.getenv("DB_READ_URL")


# Base class for all models
class Base(DeclarativeBase):
    pass

# Engine for writing (primary)
# pool_pre_ping=True: Tests connections before using them to prevent "server closed connection" errors.
write_engine = create_async_engine(WRITE_URL, pool_pre_ping=True) if WRITE_URL else None

# Engine for reading (replicas)
read_engine = create_async_engine(READ_URL, pool_pre_ping=True) if READ_URL else None

# Session factories
# expire_on_commit=False: Prevents SQLAlchemy from automatically fetching updated data 
# after a commit, which is crucial for async performance.
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

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
import os

# Database connection URL from environment variable
WRITE_URL = os.getenv("DB_WRITE_URL", "")
READ_URL = os.getenv("DB_READ_URL", "")

# Engine for writing (primary)
write_engine = create_async_engine(WRITE_URL)

# Engine for reading (replicas)
read_engine = create_async_engine(READ_URL)

# Session factories
WriteSession = async_sessionmaker(
    write_engine,
    expire_on_commit=False
)

ReadSession = async_sessionmaker(
    read_engine,
    expire_on_commit=False
)

# Base class for all models
class Base(DeclarativeBase):
    pass

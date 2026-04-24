import os

os.environ.setdefault("DB_WRITE_URL", "postgresql+asyncpg://test:test@localhost:5432/test")
os.environ.setdefault("DB_READ_URL", "postgresql+asyncpg://test:test@localhost:5432/test")
os.environ.setdefault("GOOGLE_WEB_CLIENT_ID", "test")
os.environ.setdefault("JWT_SECRET", "x" * 32)

# TEST CONFIGURATION: Sets up the environment for pytest.
# These environment variables are applied before the FastAPI app or Settings are loaded.
import os

# Use a local test database. In CI/CD, these would point to a dedicated test container.
os.environ.setdefault("DB_WRITE_URL", "postgresql+asyncpg://test:test@localhost:5432/test")
os.environ.setdefault("DB_READ_URL", "postgresql+asyncpg://test:test@localhost:5432/test")

# Placeholder credentials for testing Google Auth and JWT logic.
os.environ.setdefault("GOOGLE_WEB_CLIENT_ID", "test")
os.environ.setdefault("JWT_SECRET", "x" * 32)

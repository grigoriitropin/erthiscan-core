from functools import lru_cache
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    google_web_client_id: str = Field(alias="GOOGLE_WEB_CLIENT_ID")
    jwt_secret: str = Field(alias="JWT_SECRET", min_length=32)
    jwt_algorithm: str = "HS256"
    jwt_issuer: str = "erthiscan-core"
    jwt_audience: str = "erthiscan-app"
    jwt_expiry_seconds: int = 3600
    refresh_token_ttl_days: int = 30

    redis_url: Optional[str] = Field(default=None, alias="REDIS_URL")
    kafka_bootstrap: Optional[str] = Field(default=None, alias="KAFKA_BOOTSTRAP")

    rate_limit_auth: str = "10/minute"
    rate_limit_default: str = "120/minute"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()

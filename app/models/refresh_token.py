from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.database import Base


class RefreshToken(Base):
    """
    SECURITY MODEL: Stateful refresh tokens for JWT rotation.
    While short-lived access tokens (JWTs) are stateless and verified via cryptography, 
    long-lived refresh tokens are stored here. This allows us to instantly revoke a user's 
    ability to get new access tokens (e.g., if their device is stolen).
    """
    __tablename__ = "refresh_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    token: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

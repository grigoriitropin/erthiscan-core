from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.database import Base


class User(Base):
    """
    DATA MODEL: Represents an authenticated platform contributor.
    Users are automatically provisioned upon their first successful
    Google OAuth2 login. The 'google_id' serves as the primary external link.
    """

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    google_id: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    username: Mapped[str] = mapped_column(String, nullable=False)

from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, Float
from app.models.database import Base

class Company(Base):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    ethical_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

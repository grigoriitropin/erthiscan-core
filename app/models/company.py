from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Float, Integer, String
from app.models.database import Base


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    ethical_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    top_level_report_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    pending_vote_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

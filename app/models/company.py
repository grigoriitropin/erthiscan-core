from sqlalchemy import Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.database import Base


class Company(Base):
    """
    DATA MODEL: Represents a corporate entity.
    This is the core entity that products are linked to, and which receives 
    an aggregated 'ethical_score' based on user reports.
    """
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(primary_key=True)
    # The original name as imported from Open Food Facts.
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    # A cleaned, lowercase, unaccented version of the name.
    # We apply a pg_trgm GiST index to this column in PostgreSQL for lightning-fast fuzzy search.
    name_normalized: Mapped[str | None] = mapped_column(String, nullable=True)
    
    # Denormalized aggregate fields. We store these directly on the company row 
    # to avoid heavy COUNT/SUM queries when fetching lists of companies.
    ethical_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    top_level_report_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    
    # An optimization counter used by 'register_vote' to delay score recalculations.
    pending_vote_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

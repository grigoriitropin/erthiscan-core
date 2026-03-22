from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, SmallInteger, ForeignKey, DateTime, CheckConstraint
from sqlalchemy.dialects.postgresql import ARRAY
from datetime import datetime, timezone
from app.models.database import Base


class Report(Base):
    __tablename__ = "reports"

    __table_args__ = (
        CheckConstraint("cardinality(sources) >= 1", name="min_one_source"),
        CheckConstraint("depth IN (0, 1)", name="valid_depth"),
        CheckConstraint(
            "(depth = 0 AND parent_id IS NULL) OR (depth = 1 AND parent_id IS NOT NULL)",
            name="valid_parent_depth",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("reports.id"), nullable=True)
    depth: Mapped[int] = mapped_column(SmallInteger, default=0)
    text: Mapped[str] = mapped_column(String(150), nullable=False)
    sources: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

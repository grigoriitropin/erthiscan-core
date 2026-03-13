from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import SmallInteger, ForeignKey, UniqueConstraint, CheckConstraint
from app.models.database import Base

class Vote(Base):
    __tablename__ = "votes"

    __table_args__ = (
        UniqueConstraint("report_id", "user_id", name="one_vote_per_user"),
        CheckConstraint("value IN (1, -1)", name="valid_value"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("reports.id"), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    value: Mapped[int] = mapped_column(SmallInteger, nullable=False)

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.database import Base


class Product(Base):
    __tablename__ = "products"

    barcode: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), nullable=False)
    open_facts_url: Mapped[str | None] = mapped_column(String, nullable=True)

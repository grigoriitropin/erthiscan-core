from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.database import Base


class Product(Base):
    """
    DATA MODEL: Represents a physical product linked to a company.
    We use the 13-digit EAN barcode as the primary key because it is 
    a universal, unique identifier for consumer goods, allowing for O(1) 
    lookups when a user scans an item.
    """
    __tablename__ = "products"

    barcode: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), nullable=False)
    open_facts_url: Mapped[str | None] = mapped_column(String, nullable=True)

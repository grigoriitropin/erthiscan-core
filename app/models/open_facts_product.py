from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.database import Base


class OpenFactsProduct(Base):
    __tablename__ = "open_facts_products"

    barcode: Mapped[str] = mapped_column(String, primary_key=True)
    product_name: Mapped[str] = mapped_column(String, nullable=False)
    company_name: Mapped[str] = mapped_column(String, nullable=False)
    open_facts_url: Mapped[str | None] = mapped_column(String, nullable=True)

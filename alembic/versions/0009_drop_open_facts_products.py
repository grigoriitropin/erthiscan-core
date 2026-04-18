"""drop open_facts_products table

Revision ID: 0009_drop_open_facts_products
Revises: 0008_add_trigram_search
Create Date: 2026-04-18 00:00:00
"""

from alembic import op
import sqlalchemy as sa

revision = "0009_drop_open_facts_products"
down_revision = "0008_add_trigram_search"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("open_facts_products")


def downgrade() -> None:
    op.create_table(
        "open_facts_products",
        sa.Column("barcode", sa.String(), nullable=False, primary_key=True),
        sa.Column("product_name", sa.String(), nullable=False),
        sa.Column("company_name", sa.String(), nullable=False),
        sa.Column("open_facts_url", sa.String(), nullable=True),
    )
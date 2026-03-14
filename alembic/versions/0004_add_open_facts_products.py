"""add open facts products lookup table

Revision ID: 0004_add_open_facts_products
Revises: 0003_add_pending_vote_count
Create Date: 2026-03-14 00:00:03
"""

from alembic import op
import sqlalchemy as sa


revision = "0004_add_open_facts_products"
down_revision = "0003_add_pending_vote_count"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "open_facts_products",
        sa.Column("barcode", sa.String(), nullable=False),
        sa.Column("product_name", sa.String(), nullable=False),
        sa.Column("company_name", sa.String(), nullable=False),
        sa.Column("open_facts_url", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("barcode"),
    )


def downgrade() -> None:
    op.drop_table("open_facts_products")

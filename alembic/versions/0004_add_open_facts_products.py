"""add open facts products lookup table

Revision ID: 0004_add_open_facts_products
Revises: 0003_add_pending_vote_count
Create Date: 2026-03-14 00:00:03
"""

import sqlalchemy as sa

from alembic import op

# REVISION IDENTIFIERS: Adds external data source integration to the schema.
revision = "0004_add_open_facts_products"
down_revision = "0003_add_pending_vote_count"
branch_labels = None
depends_on = None

# NOTE: THIS MIGRATION IS MANAGED AUTOMATICALLY BY THE SERVER.


def upgrade() -> None:
    """
    UPGRADE PHASE: Creates the 'open_facts_products' table to store
    raw data dumps from external sources for faster local lookup.
    """
    op.create_table(
        "open_facts_products",
        sa.Column("barcode", sa.String(), nullable=False),
        sa.Column("product_name", sa.String(), nullable=False),
        sa.Column("company_name", sa.String(), nullable=False),
        sa.Column("open_facts_url", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("barcode"),
    )


def downgrade() -> None:
    """
    DOWNGRADE PHASE: Removes the 'open_facts_products' table.
    """
    op.drop_table("open_facts_products")

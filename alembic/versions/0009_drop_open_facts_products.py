"""drop open_facts_products table

Revision ID: 0009_drop_open_facts_products
Revises: 0008_add_trigram_search
Create Date: 2026-04-18 00:00:00
"""

import sqlalchemy as sa
from alembic import op

# REVISION IDENTIFIERS: Cleanup of the legacy data staging strategy.
revision = "0009_drop_open_facts_products"
down_revision = "0008_add_trigram_search"
branch_labels = None
depends_on = None

# NOTE: THIS MIGRATION IS MANAGED AUTOMATICALLY BY THE SERVER.

def upgrade() -> None:
    """
    UPGRADE PHASE: Drops the permanent 'open_facts_products' table.
    The import logic has been optimized to use PostgreSQL TEMP TABLES 
    during the data sync process, making this permanent staging table obsolete.
    """
    op.drop_table("open_facts_products")


def downgrade() -> None:
    """
    DOWNGRADE PHASE: Re-creates the 'open_facts_products' table 
    to support schema rollback.
    """
    op.create_table(
        "open_facts_products",
        sa.Column("barcode", sa.String(), nullable=False, primary_key=True),
        sa.Column("product_name", sa.String(), nullable=False),
        sa.Column("company_name", sa.String(), nullable=False),
        sa.Column("open_facts_url", sa.String(), nullable=True),
    )

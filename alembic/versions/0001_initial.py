"""initial core schema

Revision ID: 0001_initial
Revises: 
Create Date: 2026-03-13 00:00:00
"""

import sqlalchemy as sa
from alembic import op

# REVISION IDENTIFIERS: Unique markers for this specific schema version.
# down_revision = None indicates this is the very first migration in the history.
revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None

# NOTE: THIS MIGRATION IS MANAGED AUTOMATICALLY BY THE SERVER.
# Applied via Kubernetes Job during the GitOps synchronization process.

def upgrade() -> None:
    """
    UPGRADE PHASE: Defines the creation of the foundational database tables.
    """
    # COMPANIES: Stores organizations and their overall ethical rating.
    op.create_table(
        "companies",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("ethical_score", sa.Float(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )

    # USERS: Stores user accounts linked to Google identity.
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("google_id", sa.String(), nullable=False),
        sa.Column("username", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("google_id"),
    )

    # PRODUCTS: Maps product barcodes (EAN-13) to their respective parent companies.
    op.create_table(
        "products",
        sa.Column("barcode", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("open_facts_url", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.PrimaryKeyConstraint("barcode"),
    )


def downgrade() -> None:
    """
    DOWNGRADE PHASE: Defines how to cleanly revert the 'initial core schema' changes.
    Tables are dropped in reverse order to respect foreign key constraints.
    """
    op.drop_table("products")
    op.drop_table("users")
    op.drop_table("companies")

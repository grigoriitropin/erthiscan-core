"""add top level report count to companies

Revision ID: 0002_add_top_level_report_count
Revises: 0001_initial
Create Date: 2026-03-13 00:00:01
"""

import sqlalchemy as sa
from alembic import op

# REVISION IDENTIFIERS: Linked to the 'initial core schema' revision.
revision = "0002_add_top_level_report_count"
down_revision = "0001_initial"
branch_labels = None
depends_on = None

# NOTE: THIS MIGRATION IS MANAGED AUTOMATICALLY BY THE SERVER.

def upgrade() -> None:
    """
    UPGRADE PHASE: Adds 'top_level_report_count' to companies.
    """
    # We add the column with a server_default="0" first to handle existing rows,
    # ensuring the NOT NULL constraint isn't violated.
    op.add_column(
        "companies",
        sa.Column("top_level_report_count", sa.Integer(), nullable=False, server_default="0"),
    )
    # Then we remove the server_default so that future inserts rely on application logic.
    op.alter_column("companies", "top_level_report_count", server_default=None)


def downgrade() -> None:
    """
    DOWNGRADE PHASE: Removes the 'top_level_report_count' column.
    """
    op.drop_column("companies", "top_level_report_count")

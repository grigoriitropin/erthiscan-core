"""add pending vote count to companies

Revision ID: 0003_add_pending_vote_count
Revises: 0002_add_top_level_report_count
Create Date: 2026-03-13 00:00:02
"""

import sqlalchemy as sa
from alembic import op

# REVISION IDENTIFIERS: Sequential update to the companies table.
revision = "0003_add_pending_vote_count"
down_revision = "0002_add_top_level_report_count"
branch_labels = None
depends_on = None

# NOTE: THIS MIGRATION IS MANAGED AUTOMATICALLY BY THE SERVER.

def upgrade() -> None:
    """
    UPGRADE PHASE: Adds 'pending_vote_count' to track votes that haven't 
    yet been processed by the background scoring algorithm.
    """
    # Use server_default="0" to safely update existing rows.
    op.add_column(
        "companies",
        sa.Column("pending_vote_count", sa.Integer(), nullable=False, server_default="0"),
    )
    # Remove the server_default to keep future schema clean.
    op.alter_column("companies", "pending_vote_count", server_default=None)


def downgrade() -> None:
    """
    DOWNGRADE PHASE: Removes the 'pending_vote_count' column.
    """
    op.drop_column("companies", "pending_vote_count")

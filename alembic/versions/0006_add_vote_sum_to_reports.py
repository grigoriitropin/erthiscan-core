"""add vote_sum column to reports

Revision ID: 0006_add_vote_sum_to_reports
Revises: 0005_add_reports_and_votes
Create Date: 2026-04-03 00:00:00
"""

import sqlalchemy as sa
from alembic import op

# REVISION IDENTIFIERS: Links to the reporting/voting system migration.
revision = "0006_add_vote_sum_to_reports"
down_revision = "0005_add_reports_and_votes"
branch_labels = None
depends_on = None

# NOTE: THIS MIGRATION IS MANAGED AUTOMATICALLY BY THE SERVER.

def upgrade() -> None:
    """
    UPGRADE PHASE: Adds a denormalized 'vote_sum' column to the reports table
    to improve scoring performance by avoiding heavy JOINs on every read.
    """
    # 1. Add the column with a default value of 0.
    op.add_column("reports", sa.Column("vote_sum", sa.Integer(), server_default="0", nullable=False))

    # 2. DATA MIGRATION: Calculate and populate initial vote sums for existing reports.
    op.execute("""
        UPDATE reports SET vote_sum = COALESCE(
            (SELECT SUM(value) FROM votes WHERE votes.report_id = reports.id), 0
        )
    """)


def downgrade() -> None:
    """
    DOWNGRADE PHASE: Removes the denormalized 'vote_sum' column.
    """
    op.drop_column("reports", "vote_sum")

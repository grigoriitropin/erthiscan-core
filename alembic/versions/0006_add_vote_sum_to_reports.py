"""add vote_sum column to reports

Revision ID: 0006_add_vote_sum_to_reports
Revises: 0005_add_reports_and_votes
Create Date: 2026-04-03 00:00:00
"""

import sqlalchemy as sa

from alembic import op

revision = "0006_add_vote_sum_to_reports"
down_revision = "0005_add_reports_and_votes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("reports", sa.Column("vote_sum", sa.Integer(), server_default="0", nullable=False))

    op.execute("""
        UPDATE reports SET vote_sum = COALESCE(
            (SELECT SUM(value) FROM votes WHERE votes.report_id = reports.id), 0
        )
    """)


def downgrade() -> None:
    op.drop_column("reports", "vote_sum")

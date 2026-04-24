"""add pending vote count to companies

Revision ID: 0003_add_pending_vote_count
Revises: 0002_add_top_level_report_count
Create Date: 2026-03-13 00:00:02
"""

import sqlalchemy as sa

from alembic import op

revision = "0003_add_pending_vote_count"
down_revision = "0002_add_top_level_report_count"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "companies",
        sa.Column("pending_vote_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.alter_column("companies", "pending_vote_count", server_default=None)


def downgrade() -> None:
    op.drop_column("companies", "pending_vote_count")

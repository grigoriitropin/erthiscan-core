"""add top level report count to companies

Revision ID: 0002_add_top_level_report_count
Revises: 0001_initial
Create Date: 2026-03-13 00:00:01
"""

import sqlalchemy as sa

from alembic import op

revision = "0002_add_top_level_report_count"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "companies",
        sa.Column("top_level_report_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.alter_column("companies", "top_level_report_count", server_default=None)


def downgrade() -> None:
    op.drop_column("companies", "top_level_report_count")

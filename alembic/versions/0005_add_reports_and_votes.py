"""add reports and votes tables

Revision ID: 0005_add_reports_and_votes
Revises: 0004_add_open_facts_products
Create Date: 2026-04-02 00:00:00
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY

from alembic import op

revision = "0005_add_reports_and_votes"
down_revision = "0004_add_open_facts_products"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "reports",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("parent_id", sa.Integer(), nullable=True),
        sa.Column("depth", sa.SmallInteger(), server_default="0"),
        sa.Column("text", sa.String(150), nullable=False),
        sa.Column("sources", ARRAY(sa.String()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["parent_id"], ["reports.id"]),
        sa.CheckConstraint("cardinality(sources) >= 1", name="min_one_source"),
        sa.CheckConstraint("depth IN (0, 1)", name="valid_depth"),
        sa.CheckConstraint(
            "(depth = 0 AND parent_id IS NULL) OR (depth = 1 AND parent_id IS NOT NULL)",
            name="valid_parent_depth",
        ),
    )

    op.create_table(
        "votes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("report_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("value", sa.SmallInteger(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["report_id"], ["reports.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.UniqueConstraint("report_id", "user_id", name="one_vote_per_user"),
        sa.CheckConstraint("value IN (1, -1)", name="valid_value"),
    )


def downgrade() -> None:
    op.drop_table("votes")
    op.drop_table("reports")

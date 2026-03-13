"""initial core schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-03-13 00:00:00
"""

from alembic import op
import sqlalchemy as sa


revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "companies",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("ethical_score", sa.Float(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("google_id", sa.String(), nullable=False),
        sa.Column("username", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("google_id"),
    )

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
    op.drop_table("products")
    op.drop_table("users")
    op.drop_table("companies")

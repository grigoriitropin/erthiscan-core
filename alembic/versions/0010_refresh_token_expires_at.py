"""add expires_at and user_id index to refresh_tokens

Revision ID: 0010_refresh_token_expires_at
Revises: 0009_drop_open_facts_products
Create Date: 2026-04-24 00:00:00
"""

import sqlalchemy as sa

from alembic import op

revision = "0010_refresh_token_expires_at"
down_revision = "0009_drop_open_facts_products"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "refresh_tokens",
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_refresh_tokens_user_id",
        "refresh_tokens",
        ["user_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_refresh_tokens_user_id", table_name="refresh_tokens")
    op.drop_column("refresh_tokens", "expires_at")

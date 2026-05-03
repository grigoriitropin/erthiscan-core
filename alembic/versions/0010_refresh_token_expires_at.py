"""add expires_at and user_id index to refresh_tokens

Revision ID: 0010_refresh_token_expires_at
Revises: 0009_drop_open_facts_products
Create Date: 2026-04-24 00:00:00
"""

import sqlalchemy as sa
from alembic import op

# REVISION IDENTIFIERS: Final current migration in the version history.
revision = "0010_refresh_token_expires_at"
down_revision = "0009_drop_open_facts_products"
branch_labels = None
depends_on = None

# NOTE: THIS MIGRATION IS MANAGED AUTOMATICALLY BY THE SERVER.

def upgrade() -> None:
    """
    UPGRADE PHASE: Enhances the 'refresh_tokens' table for better security and performance.
    """
    # 1. EXPIRES_AT: Adds a timestamp to allow the application to invalidate old tokens.
    op.add_column(
        "refresh_tokens",
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    # 2. INDEXING: Adds a secondary index on 'user_id' to efficiently look up 
    # all active sessions for a specific user.
    op.create_index(
        "ix_refresh_tokens_user_id",
        "refresh_tokens",
        ["user_id"],
    )


def downgrade() -> None:
    """
    DOWNGRADE PHASE: Reverts the changes to the 'refresh_tokens' schema.
    """
    op.drop_index("ix_refresh_tokens_user_id", table_name="refresh_tokens")
    op.drop_column("refresh_tokens", "expires_at")

"""add refresh_tokens table

Revision ID: 0007_add_refresh_tokens
Revises: 0006_add_vote_sum_to_reports
Create Date: 2026-04-06 00:00:00
"""

import sqlalchemy as sa
from alembic import op

# REVISION IDENTIFIERS: Part of the authentication system update.
revision = "0007_add_refresh_tokens"
down_revision = "0006_add_vote_sum_to_reports"
branch_labels = None
depends_on = None

# NOTE: THIS MIGRATION IS MANAGED AUTOMATICALLY BY THE SERVER.

def upgrade() -> None:
    """
    UPGRADE PHASE: Creates the 'refresh_tokens' table to store secure session 
    identifiers for persistent user authentication.
    """
    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("token", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.UniqueConstraint("token"),
    )
    # INDEXING: Ensures lightning-fast token validation during the refresh flow.
    op.create_index("ix_refresh_tokens_token", "refresh_tokens", ["token"])


def downgrade() -> None:
    """
    DOWNGRADE PHASE: Removes the 'refresh_tokens' infrastructure.
    """
    op.drop_index("ix_refresh_tokens_token", table_name="refresh_tokens")
    op.drop_table("refresh_tokens")

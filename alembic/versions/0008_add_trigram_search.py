"""add pg_trgm and unaccent extensions + GIN index on companies.name

Revision ID: 0008_add_trigram_search
Revises: 0007_add_refresh_tokens
Create Date: 2026-04-17 00:00:00
"""

from alembic import op

revision = "0008_add_trigram_search"
down_revision = "0007_add_refresh_tokens"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute("CREATE EXTENSION IF NOT EXISTS unaccent")
    op.execute(
        "CREATE INDEX ix_companies_name_trgm ON companies "
        "USING gin (unaccent(name) gin_trgm_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_companies_name_trgm")
    op.execute("DROP EXTENSION IF EXISTS unaccent")
    op.execute("DROP EXTENSION IF EXISTS pg_trgm")

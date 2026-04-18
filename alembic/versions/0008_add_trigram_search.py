"""add pg_trgm and name_normalized search column

Revision ID: 0008_add_trigram_search
Revises: 0007_add_refresh_tokens
Create Date: 2026-04-17 00:00:00
"""

from alembic import op
import sqlalchemy as sa

revision = "0008_add_trigram_search"
down_revision = "0007_add_refresh_tokens"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    
    # 1. Clean up any garbage from the previously failed 0008 migration transaction
    op.execute("DROP INDEX IF EXISTS ix_companies_name_trgm")
    op.execute("DROP EXTENSION IF EXISTS unaccent")

    # 2. Add the new search column
    op.add_column('companies', sa.Column('name_normalized', sa.String(), nullable=True))
    
    # 3. Create a clean trigram GIN index on the new column
    op.execute(
        "CREATE INDEX ix_companies_name_normalized_trgm ON companies "
        "USING gin (name_normalized gin_trgm_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_companies_name_normalized_trgm")
    op.drop_column('companies', 'name_normalized')
    op.execute("DROP EXTENSION IF EXISTS pg_trgm")

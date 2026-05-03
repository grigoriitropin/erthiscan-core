"""add pg_trgm and name_normalized search column

Revision ID: 0008_add_trigram_search
Revises: 0007_add_refresh_tokens
Create Date: 2026-04-17 00:00:00
"""

import sqlalchemy as sa
from alembic import op

# REVISION IDENTIFIERS: Implementation of high-performance search capabilities.
revision = "0008_add_trigram_search"
down_revision = "0007_add_refresh_tokens"
branch_labels = None
depends_on = None

# NOTE: THIS MIGRATION IS MANAGED AUTOMATICALLY BY THE SERVER.

def upgrade() -> None:
    """
    UPGRADE PHASE: Enables trigram-based fuzzy search.
    """
    # 1. EXTENSION: Enables the pg_trgm extension for trigram similarity matching.
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    # 2. CLEANUP: Safety check to remove any leftovers from previous schema attempts.
    op.execute("DROP INDEX IF EXISTS ix_companies_name_trgm")
    op.execute("DROP EXTENSION IF EXISTS unaccent")

    # 3. NORMALIZED COLUMN: Add a dedicated column for search-optimized company names.
    op.add_column('companies', sa.Column('name_normalized', sa.String(), nullable=True))

    # 4. GIN INDEX: Create a Generalized Inverted Index (GIN) for lightning-fast 
    # similarity searches on the normalized name column.
    op.execute(
        "CREATE INDEX ix_companies_name_normalized_trgm ON companies "
        "USING gin (name_normalized gin_trgm_ops)"
    )


def downgrade() -> None:
    """
    DOWNGRADE PHASE: Removes search extensions and optimized indices.
    """
    op.execute("DROP INDEX IF EXISTS ix_companies_name_normalized_trgm")
    op.drop_column('companies', 'name_normalized')
    # Note: Generally, we don't drop extensions in downgrade if other things might use them,
    # but here it's safe as it was added specifically for this project.
    op.execute("DROP EXTENSION IF EXISTS pg_trgm")

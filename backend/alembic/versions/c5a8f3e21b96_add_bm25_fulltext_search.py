"""add bm25 fulltext search

Revision ID: c5a8f3e21b96
Revises: 3d4131e432af
Create Date: 2026-06-16 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "c5a8f3e21b96"
down_revision: Union[str, None] = "3d4131e432af"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "questions",
        sa.Column("search_vector", postgresql.TSVECTOR(), nullable=True),
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION questions_search_vector_update() RETURNS trigger AS $$
        BEGIN
            NEW.search_vector :=
                setweight(to_tsvector('english', COALESCE(NEW.text, '')), 'A') ||
                setweight(to_tsvector('english', COALESCE(NEW.reference_answer, '')), 'B');
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )

    op.execute(
        """
        CREATE TRIGGER questions_search_vector_trigger
            BEFORE INSERT OR UPDATE ON questions
            FOR EACH ROW EXECUTE FUNCTION questions_search_vector_update();
        """
    )

    op.execute(
        """
        UPDATE questions SET search_vector =
            setweight(to_tsvector('english', COALESCE(text, '')), 'A') ||
            setweight(to_tsvector('english', COALESCE(reference_answer, '')), 'B');
        """
    )

    op.execute(
        "CREATE INDEX ix_questions_search_vector ON questions USING gin(search_vector);"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_questions_search_vector;")
    op.execute("DROP TRIGGER IF EXISTS questions_search_vector_trigger ON questions;")
    op.execute("DROP FUNCTION IF EXISTS questions_search_vector_update;")
    op.drop_column("questions", "search_vector")

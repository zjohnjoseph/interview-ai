"""add hnsw index on question embeddings

Revision ID: 3d4131e432af
Revises: b518456ea551
Create Date: 2026-06-05 01:23:20.426998

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3d4131e432af'
down_revision: Union[str, None] = 'b518456ea551'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX ix_questions_embedding_hnsw ON questions "
        "USING hnsw (embedding vector_cosine_ops) "
        "WITH (m = 16, ef_construction = 64);"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_questions_embedding_hnsw;")

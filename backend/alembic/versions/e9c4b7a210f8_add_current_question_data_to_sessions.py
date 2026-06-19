"""add current_question_data to sessions

Revision ID: e9c4b7a210f8
Revises: d7a2f1c9e3b4
Create Date: 2026-06-19 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e9c4b7a210f8"
down_revision: Union[str, None] = "d7a2f1c9e3b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "candidate_sessions",
        sa.Column("current_question_data", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("candidate_sessions", "current_question_data")

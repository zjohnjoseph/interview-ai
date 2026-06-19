"""add domain to responses

Revision ID: d7a2f1c9e3b4
Revises: c5a8f3e21b96
Create Date: 2026-06-18 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d7a2f1c9e3b4"
down_revision: Union[str, None] = "c5a8f3e21b96"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "responses",
        sa.Column("domain", sa.String(length=50), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("responses", "domain")

"""add is_active column to users

Revision ID: af44bdacc830
Revises: a9c4be670396
Create Date: 2026-09-23 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'af44bdacc830'
down_revision: Union[str, None] = 'a9c4be670396'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'users',
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    # Drop the server default after backfilling existing rows, so the column
    # is a plain application-managed flag going forward rather than one that
    # silently defaults new rows at the DB layer forever.
    op.alter_column('users', 'is_active', server_default=None)


def downgrade() -> None:
    op.drop_column('users', 'is_active')
    
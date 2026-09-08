"""create users table

Revision ID: a9c4be670396
Revises: 
Create Date: 2026-09-08 10:59:14.935786

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a9c4be670396'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'users',
        sa.Column('user_id', sa.Integer(), primary_key=True, index=True),
        sa.Column('username', sa.String(length=100), nullable=False, unique=True, index=True),
        sa.Column('first_name', sa.String(length=100), nullable=False),
        sa.Column('last_name', sa.String(length=100), nullable=False),
        sa.Column('email', sa.String(length=100), nullable=False, unique=True, index=True),
        sa.Column('mobile_no', sa.String(length=20), nullable=False),
        sa.Column('password', sa.String(length=255), nullable=False),
        sa.Column('role', sa.Enum('admin', 'influencer', 'freelancer', name='userrole'), nullable=False),
        sa.Column('dob', sa.Date(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
    )


def downgrade() -> None:
    op.drop_table('users')
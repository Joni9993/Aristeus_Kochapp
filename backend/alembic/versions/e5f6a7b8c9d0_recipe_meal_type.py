"""recipe_meal_type

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-05-30 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e5f6a7b8c9d0'
down_revision: Union[str, None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add meal_type to recipes (hauptgericht | dessert | getraenk | grundrezept | sonstige)
    op.add_column('recipes', sa.Column('meal_type', sa.String(length=30), nullable=False, server_default='hauptgericht'))

    # Add include_desserts to profiles
    op.add_column('profiles', sa.Column('include_desserts', sa.Boolean(), nullable=False, server_default='0'))


def downgrade() -> None:
    op.drop_column('profiles', 'include_desserts')
    op.drop_column('recipes', 'meal_type')

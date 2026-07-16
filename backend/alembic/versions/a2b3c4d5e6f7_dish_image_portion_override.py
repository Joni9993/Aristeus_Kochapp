"""dish_image_portion_override

Revision ID: a2b3c4d5e6f7
Revises: f6a7b8c9d0e1
Create Date: 2026-07-16 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a2b3c4d5e6f7'
down_revision: Union[str, None] = 'f6a7b8c9d0e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('plan_dishes', sa.Column('image_url', sa.String(length=500), nullable=True))
    op.add_column('weekly_plans', sa.Column('portion_override', sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column('weekly_plans', 'portion_override')
    op.drop_column('plan_dishes', 'image_url')

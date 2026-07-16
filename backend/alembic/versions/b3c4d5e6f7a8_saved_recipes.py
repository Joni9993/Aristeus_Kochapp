"""saved_recipes

Revision ID: b3c4d5e6f7a8
Revises: a2b3c4d5e6f7
Create Date: 2026-07-16 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b3c4d5e6f7a8'
down_revision: Union[str, None] = 'a2b3c4d5e6f7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'saved_recipes',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('household_id', sa.Integer(), sa.ForeignKey('households.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(length=300), nullable=False),
        sa.Column('cuisine', sa.String(length=100), nullable=True),
        sa.Column('cook_time_min', sa.Integer(), nullable=True),
        sa.Column('is_favorite', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('image_url', sa.String(length=500), nullable=True),
        sa.Column('recipe_json', sa.Text(), nullable=False),
        sa.Column('source_url', sa.String(length=1000), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_saved_recipes_household_id', 'saved_recipes', ['household_id'])


def downgrade() -> None:
    op.drop_index('ix_saved_recipes_household_id', table_name='saved_recipes')
    op.drop_table('saved_recipes')

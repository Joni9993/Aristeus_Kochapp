"""recipe_catalog

Revision ID: d4e5f6a7b8c9
Revises: c2d3e4f5a6b7
Create Date: 2026-05-29 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, None] = 'c2d3e4f5a6b7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'recipes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('source', sa.String(length=50), nullable=False),
        sa.Column('source_url', sa.String(length=500), nullable=False),
        sa.Column('source_id', sa.String(length=200), nullable=True),
        sa.Column('name', sa.String(length=300), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('cuisine', sa.String(length=100), nullable=True),
        sa.Column('category', sa.String(length=100), nullable=True),
        sa.Column('cook_time_min', sa.Integer(), nullable=True),
        sa.Column('total_time_min', sa.Integer(), nullable=True),
        sa.Column('difficulty', sa.String(length=20), nullable=True),
        sa.Column('base_servings', sa.Integer(), nullable=False, server_default='4'),
        sa.Column('instructions_json', sa.Text(), nullable=False, server_default='[]'),
        sa.Column('tips_json', sa.Text(), nullable=False, server_default='[]'),
        sa.Column('image_url', sa.String(length=500), nullable=True),
        sa.Column('rating_avg', sa.Float(), nullable=True),
        sa.Column('rating_count', sa.Integer(), nullable=True),
        # Diet flags (derived at scrape time from ingredient list)
        sa.Column('is_vegetarian', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('is_vegan', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('is_meat', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('is_fish', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('contains_pork', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('contains_beef', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('contains_chicken', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('contains_turkey', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('allergen_flags_json', sa.Text(), nullable=False, server_default='[]'),
        sa.Column('meat_kinds_json', sa.Text(), nullable=False, server_default='[]'),
        sa.Column('tags_json', sa.Text(), nullable=False, server_default='[]'),
        sa.Column('scraped_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('last_seen_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('recipes', schema=None) as batch_op:
        batch_op.create_index('ix_recipes_source_url', ['source_url'], unique=True)
        batch_op.create_index('ix_recipes_cook_time', ['cook_time_min'], unique=False)
        batch_op.create_index('ix_recipes_diet', ['is_vegetarian', 'is_vegan', 'is_meat', 'is_fish'], unique=False)

    op.create_table(
        'recipe_ingredients',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('recipe_id', sa.Integer(), nullable=False),
        sa.Column('raw_name', sa.String(length=300), nullable=False),
        sa.Column('normalized_name', sa.String(length=200), nullable=False),
        sa.Column('quantity', sa.Float(), nullable=True),
        sa.Column('unit', sa.String(length=50), nullable=True),
        sa.Column('is_main', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('optional', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('notes', sa.String(length=200), nullable=True),
        sa.ForeignKeyConstraint(['recipe_id'], ['recipes.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('recipe_ingredients', schema=None) as batch_op:
        batch_op.create_index('ix_recipe_ingredients_recipe_id', ['recipe_id'], unique=False)
        batch_op.create_index('ix_recipe_ingredients_normalized', ['normalized_name'], unique=False)

    # Add recipe_id FK to plan_dishes (nullable — NULL for plans created before this migration)
    with op.batch_alter_table('plan_dishes', schema=None) as batch_op:
        batch_op.add_column(sa.Column('recipe_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_plan_dishes_recipe_id', 'recipes', ['recipe_id'], ['id'], ondelete='SET NULL')


def downgrade() -> None:
    with op.batch_alter_table('plan_dishes', schema=None) as batch_op:
        batch_op.drop_constraint('fk_plan_dishes_recipe_id', type_='foreignkey')
        batch_op.drop_column('recipe_id')

    with op.batch_alter_table('recipe_ingredients', schema=None) as batch_op:
        batch_op.drop_index('ix_recipe_ingredients_normalized')
        batch_op.drop_index('ix_recipe_ingredients_recipe_id')
    op.drop_table('recipe_ingredients')

    with op.batch_alter_table('recipes', schema=None) as batch_op:
        batch_op.drop_index('ix_recipes_diet')
        batch_op.drop_index('ix_recipes_cook_time')
        batch_op.drop_index('ix_recipes_source_url')
    op.drop_table('recipes')

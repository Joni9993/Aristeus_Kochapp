"""phase3_plans_ai

Revision ID: a1b2c3d4e5f6
Revises: 3d1466261c04
Create Date: 2026-05-28 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '3d1466261c04'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'weekly_plans',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('household_id', sa.Integer(), nullable=False),
        sa.Column('week_start_date', sa.String(length=10), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['household_id'], ['households.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('weekly_plans', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_weekly_plans_household_id'), ['household_id'], unique=False)

    op.create_table(
        'plan_dishes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('plan_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('cuisine', sa.String(length=100), nullable=True),
        sa.Column('cook_time_min', sa.Integer(), nullable=True),
        sa.Column('cook_day', sa.String(length=20), nullable=True),
        sa.Column('recipe_json', sa.Text(), nullable=True),
        sa.Column('used_offer_ids_json', sa.Text(), nullable=False),
        sa.Column('dish_status', sa.String(length=20), nullable=False),
        sa.Column('is_favorite', sa.Boolean(), nullable=False),
        sa.Column('feedback_thumbs', sa.Integer(), nullable=True),
        sa.Column('feedback_portion_note', sa.String(length=50), nullable=True),
        sa.Column('feedback_free_text', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['plan_id'], ['weekly_plans.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('plan_dishes', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_plan_dishes_plan_id'), ['plan_id'], unique=False)

    op.create_table(
        'shopping_items',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('plan_id', sa.Integer(), nullable=False),
        sa.Column('ingredient', sa.String(length=200), nullable=False),
        sa.Column('quantity', sa.String(length=50), nullable=True),
        sa.Column('unit', sa.String(length=30), nullable=True),
        sa.Column('store', sa.String(length=50), nullable=True),
        sa.Column('live_from_date', sa.String(length=20), nullable=True),
        sa.Column('offer_id', sa.Integer(), nullable=True),
        sa.Column('is_checked', sa.Boolean(), nullable=False),
        sa.Column('is_already_have', sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(['offer_id'], ['offers.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['plan_id'], ['weekly_plans.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('shopping_items', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_shopping_items_plan_id'), ['plan_id'], unique=False)

    op.create_table(
        'learned_preferences',
        sa.Column('household_id', sa.Integer(), nullable=False),
        sa.Column('loved_dishes_json', sa.Text(), nullable=False),
        sa.Column('disliked_dishes_json', sa.Text(), nullable=False),
        sa.Column('portion_adjustments_json', sa.Text(), nullable=False),
        sa.Column('recurring_notes', sa.Text(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['household_id'], ['households.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('household_id'),
    )

    op.create_table(
        'api_calls',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('household_id', sa.Integer(), nullable=True),
        sa.Column('model', sa.String(length=100), nullable=False),
        sa.Column('purpose', sa.String(length=100), nullable=True),
        sa.Column('input_tokens', sa.Integer(), nullable=False),
        sa.Column('output_tokens', sa.Integer(), nullable=False),
        sa.Column('cost_estimate', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['household_id'], ['households.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('api_calls', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_api_calls_household_id'), ['household_id'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('api_calls', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_api_calls_household_id'))
    op.drop_table('api_calls')

    op.drop_table('learned_preferences')

    with op.batch_alter_table('shopping_items', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_shopping_items_plan_id'))
    op.drop_table('shopping_items')

    with op.batch_alter_table('plan_dishes', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_plan_dishes_plan_id'))
    op.drop_table('plan_dishes')

    with op.batch_alter_table('weekly_plans', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_weekly_plans_household_id'))
    op.drop_table('weekly_plans')

"""saved_recipes_origin

Adds saved_recipes.origin ("eigene" | "gekocht") and backfills one saved_recipe
row per household for every confirmed PlanDish (with a recipe) across all of
that household's plans, deduped by case-insensitive name (newest first, by
week_start_date then dish id). Names already present in saved_recipes for a
household are skipped. This makes the cookbook (GET /api/recipes) a plain
read of saved_recipes going forward — no more merging with PlanDish at
request time, so deleting a plan no longer touches the cookbook.

Revision ID: c4d5e6f7a8b9
Revises: b3c4d5e6f7a8
Create Date: 2026-07-16 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c4d5e6f7a8b9'
down_revision: Union[str, None] = 'b3c4d5e6f7a8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'saved_recipes',
        sa.Column('origin', sa.String(length=20), nullable=False, server_default='eigene'),
    )

    conn = op.get_bind()

    # Newest first per household: dedupe keeps the first (= newest) dish seen
    # for a given case-insensitive name, matching dedupe_by_name() semantics
    # previously applied at GET /api/recipes request time.
    dish_rows = conn.execute(sa.text("""
        SELECT pd.name AS name, pd.cuisine AS cuisine, pd.cook_time_min AS cook_time_min,
               pd.is_favorite AS is_favorite, pd.image_url AS image_url, pd.recipe_json AS recipe_json,
               wp.household_id AS household_id
        FROM plan_dishes pd
        JOIN weekly_plans wp ON pd.plan_id = wp.id
        WHERE pd.dish_status = 'confirmed' AND pd.recipe_json IS NOT NULL
        ORDER BY wp.week_start_date DESC, pd.id DESC
    """)).mappings().all()

    existing_rows = conn.execute(sa.text(
        "SELECT household_id, LOWER(TRIM(name)) AS n FROM saved_recipes"
    )).mappings().all()

    seen_by_household: dict[int, set[str]] = {}
    for r in existing_rows:
        seen_by_household.setdefault(r["household_id"], set()).add(r["n"])

    to_insert = []
    for r in dish_rows:
        key = (r["name"] or "").strip().lower()
        if not key:
            continue
        hh_seen = seen_by_household.setdefault(r["household_id"], set())
        if key in hh_seen:
            continue
        hh_seen.add(key)
        to_insert.append({
            "household_id": r["household_id"],
            "name": r["name"],
            "cuisine": r["cuisine"],
            "cook_time_min": r["cook_time_min"],
            "is_favorite": r["is_favorite"],
            "image_url": r["image_url"],
            "recipe_json": r["recipe_json"],
            "origin": "gekocht",
        })

    if to_insert:
        conn.execute(
            sa.text("""
                INSERT INTO saved_recipes
                    (household_id, name, cuisine, cook_time_min, is_favorite, image_url,
                     recipe_json, source_url, origin, created_at)
                VALUES
                    (:household_id, :name, :cuisine, :cook_time_min, :is_favorite, :image_url,
                     :recipe_json, NULL, :origin, CURRENT_TIMESTAMP)
            """),
            to_insert,
        )


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM saved_recipes WHERE origin = 'gekocht'"))
    op.drop_column('saved_recipes', 'origin')

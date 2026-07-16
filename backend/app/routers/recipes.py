"""Recipes router — "Unser Kochbuch": every confirmed dish with a stored
recipe across all of a household's plans, deduped by name."""

import json

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from ..db import get_db
from ..models import Household, PlanDish, WeeklyPlan
from ..security import get_current_household

router = APIRouter(prefix="/api/recipes", tags=["recipes"])


# ---------------------------------------------------------------------------
# Pure helpers (unit-testable without a DB session)
# ---------------------------------------------------------------------------

def dedupe_by_name(dishes: list[PlanDish]) -> list[PlanDish]:
    """Keep one PlanDish per case-insensitive name.

    Callers must pass dishes ordered newest-first — the first dish seen for
    a given name is the one kept, so "neuester gewinnt".
    """
    seen: set[str] = set()
    result: list[PlanDish] = []
    for d in dishes:
        key = d.name.strip().lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(d)
    return result


def sort_dishes(dishes: list[PlanDish]) -> list[PlanDish]:
    """Favorites first, then alphabetical by name."""
    return sorted(dishes, key=lambda d: (0 if d.is_favorite else 1, d.name.strip().lower()))


def filter_dishes(
    dishes: list[PlanDish], *, q: str | None = None, favorites_only: bool = False
) -> list[PlanDish]:
    result = dishes
    if q:
        q_lower = q.strip().lower()
        result = [d for d in result if q_lower in d.name.lower()]
    if favorites_only:
        result = [d for d in result if d.is_favorite]
    return result


def _dish_out(dish: PlanDish) -> dict:
    recipe = None
    if dish.recipe_json:
        try:
            recipe = json.loads(dish.recipe_json)
        except Exception:
            pass
    return {
        "dish_id": dish.id,
        "plan_id": dish.plan_id,
        "name": dish.name,
        "cuisine": dish.cuisine,
        "cook_time_min": dish.cook_time_min,
        "is_favorite": dish.is_favorite,
        "image_url": dish.image_url or (dish.recipe.image_url if dish.recipe else None),
        "week_start_date": dish.plan.week_start_date if dish.plan else None,
        "recipe": recipe,
    }


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@router.get("")
def list_recipes(
    q: str | None = None,
    favorites_only: bool = False,
    household: Household = Depends(get_current_household),
    db: DbSession = Depends(get_db),
) -> list[dict]:
    dishes = db.scalars(
        select(PlanDish)
        .join(WeeklyPlan, PlanDish.plan_id == WeeklyPlan.id)
        .where(
            WeeklyPlan.household_id == household.id,
            PlanDish.dish_status == "confirmed",
            PlanDish.recipe_json.is_not(None),
        )
        .order_by(WeeklyPlan.week_start_date.desc(), PlanDish.id.desc())
    ).all()

    deduped = dedupe_by_name(dishes)
    filtered = filter_dishes(deduped, q=q, favorites_only=favorites_only)
    ordered = sort_dishes(filtered)

    return [_dish_out(d) for d in ordered]

"""Plans router — weekly plan lifecycle endpoints."""

import json
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from ..db import SessionLocal, get_db
from ..models import Household, PlanDish, ShoppingItem, WeeklyPlan
from ..security import get_current_household
from ..ai.pipeline import run_confirm_step, run_suggestions_step
from ..ai.learned_prefs import update_from_feedback

router = APIRouter(prefix="/api/plans", tags=["plans"])


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------

class NewPlanRequest(BaseModel):
    week_start_date: str  # YYYY-MM-DD, must be a Monday


class ConfirmSelectionRequest(BaseModel):
    selections: list[dict]  # [{dish_id: int, cook_day: str}]


class FeedbackRequest(BaseModel):
    thumbs: int | None = None        # 1 or -1
    portion_note: str | None = None  # "zu viel" | "zu wenig" | "genau richtig"
    free_text: str | None = None
    is_favorite: bool | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _dish_out(dish: PlanDish) -> dict:
    recipe = None
    if dish.recipe_json:
        try:
            recipe = json.loads(dish.recipe_json)
        except Exception:
            pass
    return {
        "id": dish.id,
        "name": dish.name,
        "description": dish.description,
        "cuisine": dish.cuisine,
        "cook_time_min": dish.cook_time_min,
        "cook_day": dish.cook_day,
        "dish_status": dish.dish_status,
        "is_favorite": dish.is_favorite,
        "feedback_thumbs": dish.feedback_thumbs,
        "feedback_portion_note": dish.feedback_portion_note,
        "feedback_free_text": dish.feedback_free_text,
        "recipe": recipe,
    }


def _item_out(item: ShoppingItem) -> dict:
    return {
        "id": item.id,
        "ingredient": item.ingredient,
        "quantity": item.quantity,
        "unit": item.unit,
        "store": item.store,
        "live_from_date": item.live_from_date,
        "is_checked": item.is_checked,
        "is_already_have": item.is_already_have,
        "is_angebot": item.store is not None,
        "price_text": item.price_text,
    }


def _plan_out(plan: WeeklyPlan, include_dishes: bool = True) -> dict:
    out: dict = {
        "id": plan.id,
        "week_start_date": plan.week_start_date,
        "status": plan.status,
        "created_at": plan.created_at.isoformat(),
    }
    if include_dishes:
        out["dishes"] = [_dish_out(d) for d in plan.dishes]
        out["shopping_items"] = [_item_out(i) for i in plan.shopping_items]
    return out


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("")
def list_plans(
    household: Household = Depends(get_current_household),
    db: DbSession = Depends(get_db),
) -> list[dict]:
    plans = db.scalars(
        select(WeeklyPlan)
        .where(WeeklyPlan.household_id == household.id)
        .order_by(WeeklyPlan.created_at.desc())
        .limit(20)
    ).all()
    return [_plan_out(p, include_dishes=False) for p in plans]


@router.post("")
def create_plan(
    body: NewPlanRequest,
    background_tasks: BackgroundTasks,
    household: Household = Depends(get_current_household),
    db: DbSession = Depends(get_db),
) -> dict:
    """Create a new weekly plan and kick off suggestion generation in the background."""
    profile = household.profile
    if not profile or not profile.postal_code:
        raise HTTPException(400, "Profil oder PLZ fehlt")
    if not profile.onboarding_complete:
        raise HTTPException(400, "Onboarding noch nicht abgeschlossen")

    plan = WeeklyPlan(
        household_id=household.id,
        week_start_date=body.week_start_date,
        status="pending",
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)

    background_tasks.add_task(_bg_suggestions, plan.id, household.id)
    return {"id": plan.id, "status": plan.status, "message": "Gerichtsvorschläge werden generiert…"}


@router.get("/{plan_id}")
def get_plan(
    plan_id: int,
    household: Household = Depends(get_current_household),
    db: DbSession = Depends(get_db),
) -> dict:
    plan = _get_plan_or_404(plan_id, household.id, db)
    return _plan_out(plan)


@router.post("/{plan_id}/more-suggestions")
async def more_suggestions(
    plan_id: int,
    household: Household = Depends(get_current_household),
    db: DbSession = Depends(get_db),
) -> dict:
    plan = _get_plan_or_404(plan_id, household.id, db)
    if plan.status not in ("suggestions_ready",):
        raise HTTPException(400, "Plan ist nicht im Vorschlagsschritt")

    dishes = await run_suggestions_step(plan_id, household, db, count=5)
    return {
        "new_suggestions": [_dish_out(d) for d in dishes],
        "total_suggestions": len(plan.dishes),
    }


@router.post("/{plan_id}/confirm")
async def confirm_plan(
    plan_id: int,
    body: ConfirmSelectionRequest,
    household: Household = Depends(get_current_household),
    db: DbSession = Depends(get_db),
) -> dict:
    """Accept selected dishes, trigger recipe + shopping list generation."""
    plan = _get_plan_or_404(plan_id, household.id, db)
    if plan.status not in ("suggestions_ready", "pending"):
        raise HTTPException(400, f"Plan status '{plan.status}' erlaubt keine Bestätigung")
    if not body.selections:
        raise HTTPException(400, "Keine Gerichte ausgewählt")

    plan = await run_confirm_step(plan_id, body.selections, household, db)
    return _plan_out(plan)


@router.delete("/{plan_id}", status_code=204)
def delete_plan(
    plan_id: int,
    household: Household = Depends(get_current_household),
    db: DbSession = Depends(get_db),
) -> None:
    plan = _get_plan_or_404(plan_id, household.id, db)
    db.delete(plan)
    db.commit()


@router.patch("/{plan_id}/dishes/{dish_id}/feedback")
def dish_feedback(
    plan_id: int,
    dish_id: int,
    body: FeedbackRequest,
    household: Household = Depends(get_current_household),
    db: DbSession = Depends(get_db),
) -> dict:
    _get_plan_or_404(plan_id, household.id, db)
    dish = db.get(PlanDish, dish_id)
    if not dish or dish.plan_id != plan_id:
        raise HTTPException(404, "Gericht nicht gefunden")

    if body.thumbs is not None:
        dish.feedback_thumbs = body.thumbs
    if body.portion_note is not None:
        dish.feedback_portion_note = body.portion_note or None
    if body.free_text is not None:
        dish.feedback_free_text = body.free_text or None
    if body.is_favorite is not None:
        dish.is_favorite = body.is_favorite

    db.commit()
    update_from_feedback(household.id, db)
    return {"ok": True}


@router.patch("/{plan_id}/shopping/{item_id}")
def update_shopping_item(
    plan_id: int,
    item_id: int,
    body: dict,
    household: Household = Depends(get_current_household),
    db: DbSession = Depends(get_db),
) -> dict:
    _get_plan_or_404(plan_id, household.id, db)
    item = db.get(ShoppingItem, item_id)
    if not item or item.plan_id != plan_id:
        raise HTTPException(404, "Item nicht gefunden")

    if "is_checked" in body:
        item.is_checked = bool(body["is_checked"])
    if "is_already_have" in body:
        item.is_already_have = bool(body["is_already_have"])

    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_plan_or_404(plan_id: int, household_id: int, db: DbSession) -> WeeklyPlan:
    plan = db.get(WeeklyPlan, plan_id)
    if not plan or plan.household_id != household_id:
        raise HTTPException(404, "Plan nicht gefunden")
    return plan


async def _bg_suggestions(plan_id: int, household_id: int) -> None:
    import logging
    log = logging.getLogger(__name__)
    db = SessionLocal()
    try:
        household = db.get(Household, household_id)
        if not household:
            return
        await run_suggestions_step(plan_id, household, db)
    except Exception as exc:
        log.error("Background suggestions failed for plan %d: %s", plan_id, exc, exc_info=True)
        plan = db.get(WeeklyPlan, plan_id)
        if plan and plan.status == "pending":
            plan.status = "error"
            plan.error_message = str(exc)[:500] if hasattr(plan, "error_message") else None
            db.commit()
    finally:
        db.close()

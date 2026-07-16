"""Plans router — weekly plan lifecycle endpoints."""

import json
import re
from datetime import date, timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from ..db import SessionLocal, get_db
from ..models import Household, Offer, PlanDish, ShoppingItem, WeeklyPlan
from ..security import get_current_household
from ..ai.pipeline import (
    apply_confirm_selection,
    run_confirm_generation,
    run_regenerate_recipe,
    run_suggestions_step,
    run_swap_dish,
)
from ..ai.learned_prefs import update_from_feedback
from ..services.status_webhook import report_incident

router = APIRouter(prefix="/api/plans", tags=["plans"])

# In-process guards against double-clicks kicking off a second background
# generation for the same plan. Fine for a single-process uvicorn deployment.
_more_suggestions_in_progress: set[int] = set()


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------

class NewPlanRequest(BaseModel):
    week_start_date: str  # YYYY-MM-DD, must be a Monday
    wish_text: str | None = None
    portion_override: int | None = None  # one-off headcount for this week (2-20), e.g. guests


class ConfirmSelectionRequest(BaseModel):
    selections: list[dict]  # [{dish_id: int, cook_day: str}]


class FeedbackRequest(BaseModel):
    thumbs: int | None = None        # 1 or -1
    portion_note: str | None = None  # "zu viel" | "zu wenig" | "genau richtig"
    free_text: str | None = None
    is_favorite: bool | None = None


class ShoppingItemCreateRequest(BaseModel):
    ingredient: str
    quantity: str | None = None
    unit: str | None = None


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
        "image_url": dish.image_url or (dish.recipe.image_url if dish.recipe else None),
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


_PRICE_RE = re.compile(r"(\d+)?[.,](\d{1,2})|(\d+)")


def _parse_price(price_text: str | None) -> float | None:
    """Parse a German offer price string into a float euro amount.

    Handles "1,99 €", "2.49", "-.99" (a bare cents amount). Returns None for
    anything that doesn't contain a parseable number instead of guessing.
    """
    if not price_text:
        return None
    match = _PRICE_RE.search(price_text.strip())
    if not match:
        return None
    if match.group(1) is not None or match.group(2) is not None:
        integer_part = match.group(1) or "0"
        decimal_part = match.group(2)
        try:
            return float(f"{integer_part}.{decimal_part}")
        except ValueError:
            return None
    try:
        return float(match.group(3))
    except (TypeError, ValueError):
        return None


def _parse_decimal(num_str: str) -> float | None:
    """"3,49" or "3.49" -> 3.49. Used on regex capture groups, which are
    already digits-plus-one-separator, so this never has to guess."""
    try:
        return float(num_str.replace(",", "."))
    except (TypeError, ValueError):
        return None


# "statt 3,49 €" / "UVP 2,99" — a crossed-out reference price near the sale
# price. Allows a little text/punctuation between the keyword and the number
# ("statt nur 3,49") but not so much it wanders into an unrelated sentence.
_REFERENCE_PRICE_RE = re.compile(r"(?:statt|uvp)\D{0,12}?(\d+(?:[.,]\d{1,2})?)", re.IGNORECASE)

# "-25%" (a leading minus sign) or "25% günstiger/billiger/...". Deliberately
# narrower than "any percentage in the text" — offers also use "%" for
# unrelated things ("25% mehr Inhalt"), which isn't a price discount.
_PERCENT_MINUS_RE = re.compile(r"-\s*(\d+(?:[.,]\d{1,2})?)\s*%")
_PERCENT_WORD_RE = re.compile(
    r"(\d+(?:[.,]\d{1,2})?)\s*%\s*(?:günstiger|billiger|sparen|rabatt|reduziert)",
    re.IGNORECASE,
)


def estimate_item_savings(price_text: str | None, hint: str | None) -> float:
    """Best-effort savings for one shopping item, derived only from the
    offer's own text (its price_text and the originating Offer.hint).

    Tries, in order:
      1. A "statt X" / "UVP X" reference price -> savings = reference − price.
      2. A discount percentage ("-25%", "25% günstiger") -> savings =
         price × p/(100−p).
    Returns 0.0 when neither pattern is found — never guesses (task 5).
    """
    current = _parse_price(price_text)
    if current is None:
        return 0.0
    haystack = " ".join(t for t in (price_text, hint) if t)
    if not haystack:
        return 0.0

    m = _REFERENCE_PRICE_RE.search(haystack)
    if m:
        reference = _parse_decimal(m.group(1))
        if reference is not None and reference > current:
            return round(reference - current, 2)

    m = _PERCENT_MINUS_RE.search(haystack) or _PERCENT_WORD_RE.search(haystack)
    if m:
        pct = _parse_decimal(m.group(1))
        if pct is not None and 0 < pct < 100:
            return round(current * pct / (100 - pct), 2)

    return 0.0


def _plan_out(plan: WeeklyPlan, db: DbSession, include_dishes: bool = True) -> dict:
    out: dict = {
        "id": plan.id,
        "week_start_date": plan.week_start_date,
        "status": plan.status,
        "wish_text": plan.wish_text,
        "portion_override": plan.portion_override,
        "created_at": plan.created_at.isoformat(),
    }
    if include_dishes:
        out["dishes"] = [_dish_out(d) for d in plan.dishes]
        out["shopping_items"] = [_item_out(i) for i in plan.shopping_items]

        offer_items = [i for i in plan.shopping_items if i.offer_id is not None]
        offer_total = sum(
            (p for p in (_parse_price(i.price_text) for i in offer_items) if p is not None),
            0.0,
        )

        estimated_savings = 0.0
        if offer_items:
            offer_ids = [i.offer_id for i in offer_items]
            offers_by_id = {
                o.id: o for o in db.scalars(select(Offer).where(Offer.id.in_(offer_ids))).all()
            }
            for item in offer_items:
                offer = offers_by_id.get(item.offer_id)
                hint = offer.hint if offer else None
                estimated_savings += estimate_item_savings(item.price_text, hint)

        out["savings"] = {
            "offers_used": len(offer_items),
            "offer_total": round(offer_total, 2),
            "estimated_savings": round(estimated_savings, 2),
        }
    return out


# ---------------------------------------------------------------------------
# Auto-complete old confirmed plans
# ---------------------------------------------------------------------------

def _should_auto_complete(week_start_date: str, today: date) -> bool:
    """A confirmed plan is auto-completed once its cook week (week_start + 7d) is over."""
    try:
        start = date.fromisoformat(week_start_date)
    except ValueError:
        return False
    return start + timedelta(days=7) < today


def _auto_complete_plans(plans: list[WeeklyPlan], db: DbSession) -> None:
    today = date.today()
    changed = False
    for plan in plans:
        if plan.status == "confirmed" and _should_auto_complete(plan.week_start_date, today):
            plan.status = "complete"
            changed = True
    if changed:
        db.commit()


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
    _auto_complete_plans(plans, db)
    return [_plan_out(p, db, include_dishes=False) for p in plans]


@router.get("/feedback-pending")
def feedback_pending(
    household: Household = Depends(get_current_household),
    db: DbSession = Depends(get_db),
) -> dict:
    """Most recent completed plan that still has a confirmed dish without feedback.

    Drives a Sunday feedback screen. Response: {"plan": <full plan> | null}.
    """
    plans = db.scalars(
        select(WeeklyPlan)
        .where(
            WeeklyPlan.household_id == household.id,
            WeeklyPlan.status.in_(["confirmed", "complete"]),
        )
        .order_by(WeeklyPlan.created_at.desc())
    ).all()
    _auto_complete_plans(plans, db)

    for plan in plans:
        if plan.status != "complete":
            continue
        if any(d.dish_status == "confirmed" and d.feedback_thumbs is None for d in plan.dishes):
            return {"plan": _plan_out(plan, db)}
    return {"plan": None}


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

    wish_text = (body.wish_text or "").strip()[:500] or None

    portion_override = body.portion_override
    if portion_override is not None and not (2 <= portion_override <= 20):
        raise HTTPException(400, "Personenzahl muss zwischen 2 und 20 liegen")

    # Reuse a pre-generated plan for this week (Sunday scheduler) — instant suggestions.
    # Confirmed/older plans for the same week are ignored, so a deliberate second
    # plan for the same week still gets fresh live suggestions.
    existing = db.scalar(
        select(WeeklyPlan)
        .where(
            WeeklyPlan.household_id == household.id,
            WeeklyPlan.week_start_date == body.week_start_date,
            WeeklyPlan.status.in_(["pending", "suggestions_ready"]),
        )
        .order_by(WeeklyPlan.id.desc())
    )
    if existing:
        if wish_text and not existing.wish_text:
            existing.wish_text = wish_text
            db.commit()
        return {"id": existing.id, "status": existing.status, "message": "Vorschläge bereits vorbereitet"}

    plan = WeeklyPlan(
        household_id=household.id,
        week_start_date=body.week_start_date,
        status="pending",
        wish_text=wish_text,
        portion_override=portion_override,
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
    _auto_complete_plans([plan], db)
    return _plan_out(plan, db)


@router.post("/{plan_id}/more-suggestions")
def more_suggestions(
    plan_id: int,
    background_tasks: BackgroundTasks,
    household: Household = Depends(get_current_household),
    db: DbSession = Depends(get_db),
) -> dict:
    """Kick off 5 more suggestions in the background — returns immediately.

    Returns {"status": "generating"} right away, matching confirm's async
    pattern; a double-click while generation is running just returns the same
    response instead of starting a second background task. The frontend is
    expected to poll GET /{plan_id} until dish count increases.
    """
    plan = _get_plan_or_404(plan_id, household.id, db)
    if plan.status not in ("suggestions_ready",):
        raise HTTPException(400, "Plan ist nicht im Vorschlagsschritt")

    if plan_id not in _more_suggestions_in_progress:
        _more_suggestions_in_progress.add(plan_id)
        background_tasks.add_task(_bg_more_suggestions, plan.id, household.id)
    return {"status": "generating"}


@router.post("/{plan_id}/confirm")
def confirm_plan(
    plan_id: int,
    body: ConfirmSelectionRequest,
    background_tasks: BackgroundTasks,
    household: Household = Depends(get_current_household),
    db: DbSession = Depends(get_db),
) -> dict:
    """Accept selected dishes; recipes + shopping list are generated in the background.

    Returns immediately with status 'confirming' — the frontend polls until
    'confirmed'. Idempotent: repeated clicks while confirming/confirmed just
    return the current plan instead of a 400.
    """
    plan = _get_plan_or_404(plan_id, household.id, db)
    if plan.status in ("confirming", "confirmed"):
        return _plan_out(plan, db)
    if plan.status not in ("suggestions_ready", "pending"):
        raise HTTPException(400, f"Plan status '{plan.status}' erlaubt keine Bestätigung")
    if not body.selections:
        raise HTTPException(400, "Keine Gerichte ausgewählt")

    apply_confirm_selection(plan, body.selections, db)
    background_tasks.add_task(_bg_confirm, plan.id, household.id)
    return _plan_out(plan, db)


@router.post("/{plan_id}/dishes/{dish_id}/swap")
def swap_dish(
    plan_id: int,
    dish_id: int,
    background_tasks: BackgroundTasks,
    household: Household = Depends(get_current_household),
    db: DbSession = Depends(get_db),
) -> dict:
    """Reject a confirmed dish and replace it with one freshly generated dish
    on the same cook_day, then rebuild the shopping list. Runs in the
    background; returns immediately with {"status": "swapping"}.
    """
    plan = _get_plan_or_404(plan_id, household.id, db)
    if plan.status != "confirmed":
        raise HTTPException(400, "Plan muss bestätigt sein, um ein Gericht zu tauschen")
    dish = db.get(PlanDish, dish_id)
    if not dish or dish.plan_id != plan_id:
        raise HTTPException(404, "Gericht nicht gefunden")
    if dish.dish_status != "confirmed":
        raise HTTPException(400, "Gericht ist nicht bestätigt")

    plan.status = "confirming"
    db.commit()
    background_tasks.add_task(_bg_swap_dish, plan.id, household.id, dish.id)
    return {"status": "swapping"}


@router.post("/{plan_id}/dishes/{dish_id}/regenerate-recipe")
def regenerate_recipe(
    plan_id: int,
    dish_id: int,
    background_tasks: BackgroundTasks,
    household: Household = Depends(get_current_household),
    db: DbSession = Depends(get_db),
) -> dict:
    """Retry recipe generation for a confirmed dish that ended up without a
    recipe (all free-tier LLM attempts 429'd during confirm). Runs in the
    background; returns immediately with {"status": "generating"}.
    """
    plan = _get_plan_or_404(plan_id, household.id, db)
    if plan.status not in ("confirmed", "complete"):
        raise HTTPException(400, "Plan muss bestätigt sein")
    dish = db.get(PlanDish, dish_id)
    if not dish or dish.plan_id != plan_id:
        raise HTTPException(404, "Gericht nicht gefunden")
    if dish.dish_status != "confirmed":
        raise HTTPException(400, "Gericht ist nicht bestätigt")
    if dish.recipe_json:
        raise HTTPException(400, "Rezept ist bereits vorhanden")

    original_status = plan.status
    plan.status = "confirming"
    db.commit()
    background_tasks.add_task(_bg_regenerate_recipe, plan.id, household.id, dish.id, original_status)
    return {"status": "generating"}


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


@router.post("/{plan_id}/shopping", status_code=201)
def create_shopping_item(
    plan_id: int,
    body: ShoppingItemCreateRequest,
    household: Household = Depends(get_current_household),
    db: DbSession = Depends(get_db),
) -> dict:
    """Add a manual (non-offer) item to a plan's shopping list."""
    _get_plan_or_404(plan_id, household.id, db)
    ingredient = body.ingredient.strip()
    if not ingredient:
        raise HTTPException(400, "Zutat fehlt")

    item = ShoppingItem(
        plan_id=plan_id,
        ingredient=ingredient,
        quantity=body.quantity,
        unit=body.unit,
        store=None,
        offer_id=None,
        is_checked=False,
        is_already_have=False,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return _item_out(item)


@router.delete("/{plan_id}/shopping/{item_id}", status_code=204)
def delete_shopping_item(
    plan_id: int,
    item_id: int,
    household: Household = Depends(get_current_household),
    db: DbSession = Depends(get_db),
) -> None:
    _get_plan_or_404(plan_id, household.id, db)
    item = db.get(ShoppingItem, item_id)
    if not item or item.plan_id != plan_id:
        raise HTTPException(404, "Item nicht gefunden")
    db.delete(item)
    db.commit()


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
            db.commit()
        await report_incident(
            f"Vorschlags-Generierung fehlgeschlagen (Plan {plan_id}, Haushalt {household_id}): {exc}"
        )
    finally:
        db.close()


async def _bg_confirm(plan_id: int, household_id: int) -> None:
    import logging
    log = logging.getLogger(__name__)
    db = SessionLocal()
    try:
        household = db.get(Household, household_id)
        if not household:
            return
        await run_confirm_generation(plan_id, household, db)
    except Exception as exc:
        # run_confirm_generation already reverted the plan on total failure
        log.error("Background confirm failed for plan %d: %s", plan_id, exc, exc_info=True)
        await report_incident(
            f"Rezept-/Einkaufslisten-Generierung fehlgeschlagen (Plan {plan_id}, Haushalt {household_id}): {exc}"
        )
    finally:
        db.close()


async def _bg_more_suggestions(plan_id: int, household_id: int) -> None:
    import logging
    log = logging.getLogger(__name__)
    db = SessionLocal()
    try:
        household = db.get(Household, household_id)
        if not household:
            return
        await run_suggestions_step(plan_id, household, db, count=5, max_desserts=1)
    except Exception as exc:
        log.error("Background more-suggestions failed for plan %d: %s", plan_id, exc, exc_info=True)
    finally:
        _more_suggestions_in_progress.discard(plan_id)
        db.close()


async def _bg_swap_dish(plan_id: int, household_id: int, dish_id: int) -> None:
    import logging
    log = logging.getLogger(__name__)
    db = SessionLocal()
    try:
        household = db.get(Household, household_id)
        if not household:
            return
        await run_swap_dish(plan_id, dish_id, household, db)
    except Exception as exc:
        # run_swap_dish already reverted plan + old dish on failure; this is
        # a last-resort net in case something failed before/after its own
        # try block (e.g. household missing).
        log.error(
            "Background swap failed for plan %d dish %d: %s", plan_id, dish_id, exc, exc_info=True
        )
        plan = db.get(WeeklyPlan, plan_id)
        if plan and plan.status == "confirming":
            plan.status = "confirmed"
            db.commit()
        old_dish = db.get(PlanDish, dish_id)
        if old_dish and old_dish.dish_status == "rejected":
            old_dish.dish_status = "confirmed"
            db.commit()
    finally:
        db.close()


async def _bg_regenerate_recipe(
    plan_id: int, household_id: int, dish_id: int, original_status: str
) -> None:
    import logging
    log = logging.getLogger(__name__)
    db = SessionLocal()
    try:
        household = db.get(Household, household_id)
        if not household:
            return
        await run_regenerate_recipe(plan_id, dish_id, household, db, original_status)
    except Exception as exc:
        # run_regenerate_recipe already reverted the plan status on failure;
        # this is a last-resort net in case something failed before its own
        # try block (e.g. household missing).
        log.error(
            "Background recipe regeneration failed for plan %d dish %d: %s",
            plan_id, dish_id, exc, exc_info=True,
        )
        plan = db.get(WeeklyPlan, plan_id)
        if plan and plan.status == "confirming":
            plan.status = original_status
            db.commit()
    finally:
        db.close()

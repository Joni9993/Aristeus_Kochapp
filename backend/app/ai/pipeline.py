"""8-step AI pipeline for weekly plan generation.

Steps:
  1. Filter cooking-relevant offers (optionally monday-only)
  2. Build learning context from feedback history
  3. Generate dish suggestions via LLM (10 initial, +5 on demand)
  4. Validate suggestions (diet / allergy / cooktime)
  5. User selects dishes + assigns days (UI — split point)
  6. Generate recipes in parallel (one LLM call per dish)
  7. Aggregate shopping list
  8. Weekly feedback aggregation (separate scheduled call)
"""

import asyncio
import json
import logging

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from ..models import (
    ApiCall,
    Brochure,
    Household,
    Offer,
    PlanDish,
    ShoppingItem,
    WeeklyPlan,
)
from .client import chat_completion_json
from .learned_prefs import build_learn_context
from .prompts import (
    build_recipe_prompt,
    build_suggestions_prompt,
    format_offers,
    format_profile,
)
from .schemas import DishSuggestion, DishSuggestionsResponse, RecipeResponse
from .validators import validate_suggestions

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Step 1: Filter offers
# ---------------------------------------------------------------------------

def _get_active_offers(plz: str, stores: list[str], db: DbSession) -> list[Offer]:
    """Return cooking-relevant offers from the most recent active brochure per store."""
    result: list[Offer] = []
    for store in stores:
        brochure = db.scalar(
            select(Brochure)
            .where(
                Brochure.store == store,
                Brochure.postal_code == plz,
                Brochure.status == "active",
            )
            .order_by(Brochure.fetched_at.desc())
            .limit(1)
        )
        if not brochure:
            continue
        for offer in brochure.offers:
            if offer.is_cooking_relevant:
                result.append(offer)
    return result


def _filter_monday_only(offers: list[Offer], week_start: str) -> list[Offer]:
    """Keep offers that are valid from the week_start date (monday) onwards."""
    filtered = []
    for o in offers:
        if not o.live_from_date:
            filtered.append(o)
            continue
        if o.live_from_date <= week_start:
            filtered.append(o)
    return filtered


# ---------------------------------------------------------------------------
# Step 3: Generate suggestions
# ---------------------------------------------------------------------------

async def generate_suggestions(
    *,
    household: Household,
    plan: WeeklyPlan,
    db: DbSession,
    count: int = 10,
    exclude_names: list[str] | None = None,
) -> list[DishSuggestion]:
    profile = household.profile
    plz = profile.postal_code
    stores = json.loads(profile.selected_stores_json or "[]")

    offers = _get_active_offers(plz, stores, db)
    if profile.monday_only_offers:
        offers = _filter_monday_only(offers, plan.week_start_date)

    learn_ctx = build_learn_context(household.id, db)
    profile_text = format_profile(profile)
    offers_text = format_offers(offers)

    messages = build_suggestions_prompt(
        offers_text=offers_text,
        profile_text=profile_text,
        learn_text=learn_ctx,
        count=count,
        week_start=plan.week_start_date,
        exclude_names=exclude_names,
    )

    raw, model, usage = await chat_completion_json(messages, purpose="dish_suggestions")
    _log_api_call(household.id, model, usage, "dish_suggestions", db)

    try:
        parsed = DishSuggestionsResponse.model_validate(raw)
    except (ValidationError, Exception) as exc:
        logger.error("Suggestions parse error: %s — raw: %s", exc, str(raw)[:500])
        return []

    # Step 4: validate
    valid = validate_suggestions(parsed.vorschlaege, profile)
    logger.info(
        "Suggestions: %d from LLM → %d after validation (plan %d)",
        len(parsed.vorschlaege), len(valid), plan.id,
    )
    return valid


# ---------------------------------------------------------------------------
# Step 6: Generate recipes
# ---------------------------------------------------------------------------

async def generate_recipe_for_dish(
    dish: PlanDish,
    household: Household,
    db: DbSession,
) -> RecipeResponse | None:
    profile = household.profile
    plz = profile.postal_code
    stores = json.loads(profile.selected_stores_json or "[]")

    offers = _get_active_offers(plz, stores, db)
    offers_text = format_offers(offers)
    profile_text = format_profile(profile)

    messages = build_recipe_prompt(
        dish_name=dish.name,
        dish_description=dish.description or "",
        profile_text=profile_text,
        offers_text=offers_text,
    )

    raw, model, usage = await chat_completion_json(messages, purpose="recipe_gen")
    _log_api_call(household.id, model, usage, "recipe_gen", db)

    try:
        return RecipeResponse.model_validate(raw)
    except (ValidationError, Exception) as exc:
        logger.error("Recipe parse error for '%s': %s", dish.name, exc)
        return None


async def generate_recipes_parallel(
    dishes: list[PlanDish],
    household: Household,
    db: DbSession,
) -> dict[int, RecipeResponse]:
    """Generate recipes for all confirmed dishes in parallel."""
    tasks = [generate_recipe_for_dish(d, household, db) for d in dishes]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    recipes: dict[int, RecipeResponse] = {}
    for dish, result in zip(dishes, results):
        if isinstance(result, Exception):
            logger.error("Recipe generation failed for '%s': %s", dish.name, result)
        elif result is not None:
            recipes[dish.id] = result
            dish.recipe_json = result.model_dump_json()
    return recipes


# ---------------------------------------------------------------------------
# Step 7: Aggregate shopping list
# ---------------------------------------------------------------------------

_KNOWN_STORES = {"rewe", "lidl", "aldi", "edeka", "penny", "netto", "kaufland"}


def _normalize_store(laden: str) -> str | None:
    """Map AI-reported store name ('Lidl', 'Aldi Süd') to the DB key ('lidl', 'aldi')."""
    lower = laden.lower().strip()
    for s in _KNOWN_STORES:
        if s in lower:
            return s
    return None


def _find_matching_offer(name_lower: str, offers: list[Offer]) -> Offer | None:
    """Find the best-matching offer for an ingredient name."""
    # Exact match first
    for o in offers:
        if o.product_name.lower() == name_lower:
            return o
    # Substring: ingredient name is contained in offer name or vice versa
    for o in offers:
        offer_lower = o.product_name.lower()
        if name_lower in offer_lower or offer_lower in name_lower:
            return o
    # Word-based fallback: 2+ significant words in common
    name_words = {w for w in name_lower.split() if len(w) > 3}
    if name_words:
        for o in offers:
            offer_words = {w for w in o.product_name.lower().split() if len(w) > 3}
            if len(name_words & offer_words) >= 2:
                return o
    return None


def build_shopping_list(
    plan: WeeklyPlan,
    recipes: dict[int, RecipeResponse],
    household: Household,
    db: DbSession,
) -> list[ShoppingItem]:
    """Aggregate ingredients from all recipe responses into shopping items."""
    # Load active offers to resolve store for angebot ingredients
    profile = household.profile
    active_offers: list[Offer] = []
    if profile and profile.postal_code:
        stores = json.loads(profile.selected_stores_json or "[]")
        active_offers = _get_active_offers(profile.postal_code, stores, db)

    # Aggregate by (ingredient_name_lower, unit)
    aggregated: dict[tuple[str, str], dict] = {}

    for dish in plan.dishes:
        if dish.dish_status != "confirmed":
            continue
        recipe = recipes.get(dish.id)
        if not recipe:
            continue
        for ing in recipe.zutaten:
            key = (ing.name.strip().lower(), (ing.einheit or "").lower())
            if key not in aggregated:
                aggregated[key] = {
                    "name": ing.name.strip(),
                    "total": 0.0,
                    "unit": ing.einheit,
                    "is_angebot": ing.ist_angebot,
                    "laden": ing.laden,  # AI-reported store name
                }
            if ing.menge:
                aggregated[key]["total"] += ing.menge

    items: list[ShoppingItem] = []
    for entry in aggregated.values():
        qty_rounded = round(entry["total"])
        qty = str(qty_rounded) if qty_rounded > 0 else None

        store: str | None = None
        offer_id: int | None = None
        price_text: str | None = None

        if entry["is_angebot"]:
            # Primary: use AI-reported store name
            if entry["laden"]:
                store = _normalize_store(entry["laden"])
            # Find matching offer for offer_id and price_text
            if active_offers:
                matched = _find_matching_offer(entry["name"].lower(), active_offers)
                if matched:
                    offer_id = matched.id
                    price_text = matched.price_text
                    if not store:  # fallback if AI didn't report laden
                        store = matched.store

        item = ShoppingItem(
            plan_id=plan.id,
            ingredient=entry["name"],
            quantity=qty,
            unit=entry["unit"],
            store=store,
            offer_id=offer_id,
            price_text=price_text,
            is_checked=False,
            is_already_have=False,
        )
        db.add(item)
        items.append(item)

    db.flush()
    logger.info("Built shopping list: %d items for plan %d", len(items), plan.id)
    return items


# ---------------------------------------------------------------------------
# Full pipeline entrypoints
# ---------------------------------------------------------------------------

async def run_suggestions_step(
    plan_id: int,
    household: Household,
    db: DbSession,
    count: int = 10,
) -> list[PlanDish]:
    """Steps 1-4: Generate and persist suggestions. Returns saved PlanDish rows."""
    plan = db.get(WeeklyPlan, plan_id)
    if not plan:
        raise ValueError(f"Plan {plan_id} not found")

    existing_names = [d.name for d in plan.dishes if d.dish_status == "suggestion"]
    suggestions = await generate_suggestions(
        household=household,
        plan=plan,
        db=db,
        count=count,
        exclude_names=existing_names if existing_names else None,
    )

    saved: list[PlanDish] = []
    for s in suggestions:
        dish = PlanDish(
            plan_id=plan.id,
            name=s.name,
            description=s.beschreibung,
            cuisine=s.kategorie,
            cook_time_min=s.kochzeit_min,
            dish_status="suggestion",
            used_offer_ids_json="[]",
        )
        db.add(dish)
        saved.append(dish)

    db.flush()
    plan.status = "suggestions_ready"
    db.commit()
    return saved


async def run_confirm_step(
    plan_id: int,
    selections: list[dict],  # [{dish_id: int, cook_day: str}]
    household: Household,
    db: DbSession,
) -> WeeklyPlan:
    """Steps 5-7: Confirm selections, generate recipes, build shopping list."""
    plan = db.get(WeeklyPlan, plan_id)
    if not plan:
        raise ValueError(f"Plan {plan_id} not found")

    # Mark confirmed dishes
    selection_map = {s["dish_id"]: s.get("cook_day") for s in selections}
    confirmed: list[PlanDish] = []
    for dish in plan.dishes:
        if dish.id in selection_map:
            dish.dish_status = "confirmed"
            dish.cook_day = selection_map[dish.id]
            confirmed.append(dish)
        else:
            dish.dish_status = "rejected"

    db.flush()

    # Step 6: recipes
    recipes = await generate_recipes_parallel(confirmed, household, db)

    # Step 7: shopping list
    build_shopping_list(plan, recipes, household, db)

    plan.status = "confirmed"
    db.commit()
    return plan


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _log_api_call(
    household_id: int,
    model: str,
    usage: dict,
    purpose: str,
    db: DbSession,
) -> None:
    try:
        db.add(ApiCall(
            household_id=household_id,
            model=model,
            purpose=purpose,
            input_tokens=usage.get("prompt_tokens", 0),
            output_tokens=usage.get("completion_tokens", 0),
            cost_estimate=0,
        ))
        db.flush()
    except Exception as exc:
        logger.warning("Failed to log api call: %s", exc)

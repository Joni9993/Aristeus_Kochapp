"""AI pipeline for weekly plan generation.

Steps:
  1. Filter cooking-relevant offers
  2. Build learning context from feedback history (for scoring)
  3. Suggest dishes from recipe catalog (deterministic, no LLM)
  4. (Validation built into matcher filters)
  5. User selects dishes + assigns days (UI — split point)
  6. Load recipe from catalog + scale to household size (no LLM)
  7. Aggregate shopping list
  8. Weekly feedback aggregation (separate scheduled call — still uses LLM)

Old LLM paths for steps 3 and 6 are kept as fallback for plans created
before the recipe catalog (dish.recipe_id IS NULL).
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
    Recipe,
    RecipeIngredient,
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
from .schemas import DishSuggestionsResponse, RecipeIngredient as SchemaIngredient, RecipeResponse
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
    filtered = []
    for o in offers:
        if not o.live_from_date:
            filtered.append(o)
            continue
        if o.live_from_date <= week_start:
            filtered.append(o)
    return filtered


# ---------------------------------------------------------------------------
# Step 3: Suggest dishes from catalog (deterministic)
# ---------------------------------------------------------------------------

async def generate_suggestions(
    *,
    household: Household,
    plan: WeeklyPlan,
    db: DbSession,
    count: int = 10,
    exclude_names: list[str] | None = None,
    max_desserts: int = 2,
) -> list[dict]:
    """Return suggestion dicts from the recipe catalog.

    Each dict has keys: name, beschreibung, kategorie, kochzeit_min, recipe_id.
    Falls back to LLM if catalog is empty.
    """
    from ..services.recipe_matcher import suggest_dishes, ScoredRecipe

    # Collect recipe_ids already suggested on this plan
    existing_recipe_ids = [
        d.recipe_id for d in plan.dishes
        if d.dish_status == "suggestion" and d.recipe_id is not None
    ]

    scored = suggest_dishes(
        household=household,
        plan=plan,
        db=db,
        count=count,
        exclude_recipe_ids=existing_recipe_ids or None,
        max_desserts=max_desserts,
    )

    if scored:
        results = []
        for sr in scored:
            r = sr.recipe
            reasons_str = ", ".join(sr.match_reasons) if sr.match_reasons else ""
            results.append({
                "name": r.name,
                "beschreibung": (r.description or reasons_str or "")[:300],
                "kategorie": _map_diet_category(r),
                "kochzeit_min": r.cook_time_min or 30,
                "recipe_id": r.id,
            })
        return results

    # Fallback: catalog empty → LLM
    logger.warning("Recipe catalog empty — falling back to LLM suggestions for plan %d", plan.id)
    return await _llm_suggestions_fallback(household=household, plan=plan, db=db, count=count, exclude_names=exclude_names)


def _map_diet_category(recipe: Recipe) -> str:
    if recipe.is_vegan:
        return "vegan"
    if recipe.is_vegetarian:
        return "vegetarisch"
    if recipe.is_fish and not recipe.is_meat:
        return "Fisch"
    if recipe.is_meat:
        return "Fleisch"
    return "gemischt"


# ---------------------------------------------------------------------------
# LLM fallback for suggestions (old Step 3)
# ---------------------------------------------------------------------------

async def _llm_suggestions_fallback(
    *,
    household: Household,
    plan: WeeklyPlan,
    db: DbSession,
    count: int,
    exclude_names: list[str] | None,
) -> list[dict]:
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

    valid = validate_suggestions(parsed.vorschlaege, profile)
    return [
        {
            "name": s.name,
            "beschreibung": s.beschreibung,
            "kategorie": s.kategorie,
            "kochzeit_min": s.kochzeit_min,
            "recipe_id": None,
        }
        for s in valid
    ]


# ---------------------------------------------------------------------------
# Step 6: Load recipe from catalog + scale
# ---------------------------------------------------------------------------

_COUNTABLE_UNITS = {None, ""}  # eggs, onions, cloves, packets without a unit


def _round_quantity(qty: float, unit: str | None) -> float:
    """Round a scaled quantity to a kitchen-friendly value."""
    u = (unit or "").lower().strip()

    # Countable items (Eier, Zwiebeln, Zehen, Pck., …) → nearest integer, min 1
    if u in ("", "stück", "stk", "pck", "pck.", "pkg"):
        return max(1.0, round(qty))

    # Pinches / small counts → nearest 0.5
    if u in ("prise", "prisen", "msp", "mssp", "zehe", "zehen", "bund", "bunde"):
        return max(0.5, round(qty * 2) / 2)

    # Small spoon measures (tl, el) → nearest 0.25
    if u in ("tl", "el"):
        return max(0.25, round(qty * 4) / 4)

    # Cup / glass / can → nearest 0.5
    if u in ("tasse", "tassen", "glas", "dose", "dosen", "becher", "beutel"):
        return max(0.5, round(qty * 2) / 2)

    # Liquid (ml, cl, dl, l) → nearest 5ml equivalent
    if u in ("ml", "cl", "dl"):
        step = 5 if u == "ml" else (1 if u == "cl" else 0.5)
        return max(step, round(qty / step) * step)
    if u == "l":
        return max(0.1, round(qty * 10) / 10)

    # Weight (g, kg, mg)
    if u == "g":
        if qty < 10:
            return max(1.0, round(qty))
        if qty < 50:
            return max(5.0, round(qty / 5) * 5)
        return max(10.0, round(qty / 10) * 10)
    if u == "kg":
        return max(0.1, round(qty * 10) / 10)

    # Default: 1 decimal
    return round(qty, 1)


def _load_recipe_from_catalog(
    dish: PlanDish,
    household: Household,
    db: DbSession,
) -> RecipeResponse | None:
    """Build a RecipeResponse by scaling catalog ingredients to household size."""
    recipe: Recipe | None = db.get(Recipe, dish.recipe_id)
    if not recipe:
        return None

    profile = household.profile

    # Children count as 0.5 portions (cleaner fractions, realistic for smaller appetites)
    person_count = profile.adults + profile.kids * 0.5

    # base_servings=1 usually means chefkoch returned "1 Blech/Torte" — treat as 4
    effective_servings = recipe.base_servings if recipe.base_servings >= 2 else 4
    scale = person_count / effective_servings

    # Load all ingredients
    ings: list[RecipeIngredient] = list(db.scalars(
        select(RecipeIngredient).where(RecipeIngredient.recipe_id == recipe.id)
    ).all())

    # Match ingredients against active offers
    stores: list[str] = json.loads(profile.selected_stores_json or "[]")
    active_offers = _get_active_offers(profile.postal_code or "", stores, db)

    from ..services.recipe_matcher import find_matching_offer

    schema_ings: list[SchemaIngredient] = []
    for ing in ings:
        offer = find_matching_offer(ing.normalized_name, active_offers)
        if ing.quantity:
            scaled_qty = _round_quantity(ing.quantity * scale, ing.unit)
        else:
            scaled_qty = None
        schema_ings.append(SchemaIngredient(
            name=ing.raw_name,
            menge=scaled_qty,
            einheit=ing.unit,
            ist_angebot=offer is not None,
            laden=offer.store.capitalize() if offer else None,
        ))

    steps: list[str] = json.loads(recipe.instructions_json or "[]")
    tips: list[str] = json.loads(recipe.tips_json or "[]")

    return RecipeResponse(
        zutaten=schema_ings,
        schritte=steps,
        geschaetzte_zeit_min=recipe.cook_time_min or 30,
        tipps=tips,
    )


async def generate_recipe_for_dish(
    dish: PlanDish,
    household: Household,
    db: DbSession,
) -> RecipeResponse | None:
    # New path: catalog
    if dish.recipe_id is not None:
        result = _load_recipe_from_catalog(dish, household, db)
        if result:
            return result
        logger.warning(
            "Catalog recipe %d missing for dish '%s' — falling back to LLM",
            dish.recipe_id, dish.name,
        )

    # Fallback: LLM (old plans or catalog miss)
    return await _llm_recipe_fallback(dish, household, db)


async def _llm_recipe_fallback(
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
    """Generate/load recipes for all confirmed dishes."""
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
    lower = laden.lower().strip()
    for s in _KNOWN_STORES:
        if s in lower:
            return s
    return None


def _find_matching_offer(name_lower: str, offers: list[Offer]) -> Offer | None:
    """Find the best-matching offer for an ingredient name (kept public for recipe_matcher)."""
    for o in offers:
        if o.product_name.lower() == name_lower:
            return o
    for o in offers:
        offer_lower = o.product_name.lower()
        if name_lower in offer_lower or offer_lower in name_lower:
            return o
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
    profile = household.profile
    active_offers: list[Offer] = []
    if profile and profile.postal_code:
        stores = json.loads(profile.selected_stores_json or "[]")
        active_offers = _get_active_offers(profile.postal_code, stores, db)

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
                    "laden": ing.laden,
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
            if entry["laden"]:
                store = _normalize_store(entry["laden"])
            if active_offers:
                matched = _find_matching_offer(entry["name"].lower(), active_offers)
                if matched:
                    offer_id = matched.id
                    price_text = matched.price_text
                    if not store:
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
    max_desserts: int = 2,
) -> list[PlanDish]:
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
        max_desserts=max_desserts,
    )

    saved: list[PlanDish] = []
    for s in suggestions:
        dish = PlanDish(
            plan_id=plan.id,
            name=s["name"],
            description=s["beschreibung"],
            cuisine=s.get("kategorie"),
            cook_time_min=s.get("kochzeit_min", 30),
            dish_status="suggestion",
            used_offer_ids_json="[]",
            recipe_id=s.get("recipe_id"),
        )
        db.add(dish)
        saved.append(dish)

    db.flush()
    plan.status = "suggestions_ready"
    db.commit()
    return saved


async def run_confirm_step(
    plan_id: int,
    selections: list[dict],
    household: Household,
    db: DbSession,
) -> WeeklyPlan:
    plan = db.get(WeeklyPlan, plan_id)
    if not plan:
        raise ValueError(f"Plan {plan_id} not found")

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

    recipes = await generate_recipes_parallel(confirmed, household, db)
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

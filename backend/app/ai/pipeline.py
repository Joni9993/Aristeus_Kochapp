"""AI pipeline for weekly plan generation.

Steps:
  1. Filter cooking-relevant offers
  2. Build learning context from feedback history
  3. LLM suggests dishes (offers + profile + learned preferences + anti-repetition)
  4. Deterministic validation (diet, allergies, cook time)
  5. User selects dishes + assigns days (UI — split point)
  6. LLM generates full recipes for confirmed dishes (parallel)
  7. Aggregate shopping list
  8. Weekly feedback aggregation (separate scheduled call)

The Chefkoch recipe catalog path is deactivated (settings.use_recipe_catalog,
default false) — the LLM is the primary suggestion/recipe source. Catalog code
is kept behind the flag and for old plans whose dishes carry a recipe_id.
"""

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
# Step 3: Suggest dishes (LLM primary; catalog only behind use_recipe_catalog)
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
    """Return suggestion dicts, each with keys:
    name, beschreibung, kategorie, kochzeit_min, recipe_id.
    """
    from ..config import get_settings

    if get_settings().use_recipe_catalog:
        catalog = _catalog_suggestions(
            household=household, plan=plan, db=db,
            count=count, max_desserts=max_desserts,
        )
        if catalog:
            return catalog
        logger.warning("Recipe catalog empty — falling back to LLM for plan %d", plan.id)

    return await _llm_suggestions(
        household=household, plan=plan, db=db,
        count=count, exclude_names=exclude_names,
    )


def _catalog_suggestions(
    *,
    household: Household,
    plan: WeeklyPlan,
    db: DbSession,
    count: int,
    max_desserts: int,
) -> list[dict]:
    """Deactivated Chefkoch catalog path — only used when use_recipe_catalog=true."""
    from ..services.recipe_matcher import suggest_dishes

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
# LLM suggestions (primary path)
# ---------------------------------------------------------------------------

def _recent_dish_names(household: Household, plan: WeeklyPlan, db: DbSession, limit: int = 30) -> list[str]:
    """Dish names from recent plans — confirmed dishes from the last 8 weeks plus
    everything suggested on the last 2 plans, so suggestions rotate week to week."""
    from datetime import date, timedelta

    names: list[str] = []
    seen: set[str] = set()

    cutoff = (date.today() - timedelta(weeks=8)).isoformat()
    confirmed = db.scalars(
        select(PlanDish)
        .join(WeeklyPlan)
        .where(
            WeeklyPlan.household_id == household.id,
            WeeklyPlan.id != plan.id,
            WeeklyPlan.week_start_date >= cutoff,
            PlanDish.dish_status == "confirmed",
        )
    ).all()

    recent_plans = db.scalars(
        select(WeeklyPlan)
        .where(WeeklyPlan.household_id == household.id, WeeklyPlan.id != plan.id)
        .order_by(WeeklyPlan.id.desc())
        .limit(2)
    ).all()
    suggested = [d for p in recent_plans for d in p.dishes]

    for d in confirmed + suggested:
        key = d.name.strip().lower()
        if key and key not in seen:
            seen.add(key)
            names.append(d.name.strip())
        if len(names) >= limit:
            break
    return names


async def _llm_suggestions(
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

    # Anti-repetition: same-plan suggestions + dishes from recent weeks
    avoid = list(exclude_names or [])
    for name in _recent_dish_names(household, plan, db):
        if name not in avoid:
            avoid.append(name)

    messages = build_suggestions_prompt(
        offers_text=offers_text,
        profile_text=profile_text,
        learn_text=learn_ctx,
        count=count,
        week_start=plan.week_start_date,
        exclude_names=avoid or None,
    )

    raw, model, usage = await chat_completion_json(
        messages, purpose="dish_suggestions", temperature=0.9, max_tokens=5000,
    )
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
    from ..config import get_settings

    # Catalog path only for old dishes carrying a recipe_id AND if re-enabled
    if get_settings().use_recipe_catalog and dish.recipe_id is not None:
        result = _load_recipe_from_catalog(dish, household, db)
        if result:
            return result
        logger.warning(
            "Catalog recipe %d missing for dish '%s' — falling back to LLM",
            dish.recipe_id, dish.name,
        )

    # Primary path: LLM
    return await _llm_recipe(dish, household, db)


async def _llm_recipe(
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

    raw, model, usage = await chat_completion_json(messages, purpose="recipe_gen", max_tokens=4000)
    _log_api_call(household.id, model, usage, "recipe_gen", db)

    try:
        return RecipeResponse.model_validate(raw)
    except (ValidationError, Exception) as exc:
        logger.error("Recipe parse error for '%s': %s", dish.name, exc)
        return None


_RECIPE_BATCH_SIZE = 4  # dishes per LLM call — keeps responses parseable


async def _llm_recipes_batch(
    dishes: list[PlanDish],
    household: Household,
    db: DbSession,
) -> dict[int, RecipeResponse]:
    """One LLM call for a chunk of dishes. Returns {dish_id: recipe} for all matched."""
    from .prompts import build_recipes_batch_prompt
    from .schemas import RecipesBatchResponse

    profile = household.profile
    stores = json.loads(profile.selected_stores_json or "[]")
    offers = _get_active_offers(profile.postal_code or "", stores, db)

    messages = build_recipes_batch_prompt(
        dishes=[(d.name, d.description or "") for d in dishes],
        profile_text=format_profile(profile),
        offers_text=format_offers(offers),
    )

    # ~1200 tokens per recipe JSON + generous headroom for reasoning models —
    # a too-tight limit truncates the JSON and wastes the whole batch call
    raw, model, usage = await chat_completion_json(
        messages, purpose="recipe_batch", max_tokens=1500 * len(dishes) + 2500,
    )
    _log_api_call(household.id, model, usage, "recipe_batch", db)

    try:
        parsed = RecipesBatchResponse.model_validate(raw)
    except (ValidationError, Exception) as exc:
        logger.error("Recipe batch parse error: %s", exc)
        return {}

    by_name = {r.gericht.strip().lower(): r for r in parsed.rezepte}
    result: dict[int, RecipeResponse] = {}
    for dish in dishes:
        entry = by_name.get(dish.name.strip().lower())
        if entry:
            result[dish.id] = RecipeResponse(
                zutaten=entry.zutaten,
                schritte=entry.schritte,
                geschaetzte_zeit_min=entry.geschaetzte_zeit_min,
                tipps=entry.tipps,
            )
    return result


def _recipe_from_stored_json(dish: PlanDish) -> RecipeResponse | None:
    if not dish.recipe_json:
        return None
    try:
        return RecipeResponse.model_validate_json(dish.recipe_json)
    except (ValidationError, Exception):
        return None


async def generate_recipes(
    dishes: list[PlanDish],
    household: Household,
    db: DbSession,
) -> dict[int, RecipeResponse]:
    """Return recipes for the given dishes.

    Order: reuse pre-generated recipe_json → catalog (if flag on) → LLM in
    batches of _RECIPE_BATCH_SIZE (one call per chunk instead of one per dish)
    → individual LLM call for anything the batch response missed.
    """
    from ..config import get_settings

    recipes: dict[int, RecipeResponse] = {}
    need_llm: list[PlanDish] = []

    use_catalog = get_settings().use_recipe_catalog
    for dish in dishes:
        stored = _recipe_from_stored_json(dish)
        if stored:
            recipes[dish.id] = stored
            continue
        if use_catalog and dish.recipe_id is not None:
            loaded = _load_recipe_from_catalog(dish, household, db)
            if loaded:
                recipes[dish.id] = loaded
                dish.recipe_json = loaded.model_dump_json()
                continue
        need_llm.append(dish)

    # Batched LLM calls, chunks run sequentially (gentler on free-tier limits)
    for i in range(0, len(need_llm), _RECIPE_BATCH_SIZE):
        chunk = need_llm[i:i + _RECIPE_BATCH_SIZE]
        try:
            batch_result = await _llm_recipes_batch(chunk, household, db)
        except Exception as exc:
            logger.error("Recipe batch call failed: %s", exc)
            batch_result = {}
        for dish in chunk:
            recipe = batch_result.get(dish.id)
            if recipe is None:
                # Batch missed this dish — one individual call as fallback
                try:
                    recipe = await _llm_recipe(dish, household, db)
                except Exception as exc:
                    logger.error("Recipe generation failed for '%s': %s", dish.name, exc)
                    recipe = None
            if recipe is not None:
                recipes[dish.id] = recipe
                dish.recipe_json = recipe.model_dump_json()

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


def apply_confirm_selection(
    plan: WeeklyPlan,
    selections: list[dict],
    db: DbSession,
) -> None:
    """Synchronous part of confirm: mark dishes + set status 'confirming'.

    Committing this immediately makes a double-click idempotent — the second
    request sees status 'confirming' and just returns the plan.
    """
    selection_map = {s["dish_id"]: s.get("cook_day") for s in selections}
    for dish in plan.dishes:
        if dish.id in selection_map:
            dish.dish_status = "confirmed"
            dish.cook_day = selection_map[dish.id]
        elif dish.dish_status == "suggestion":
            dish.dish_status = "rejected"
    plan.status = "confirming"
    db.commit()


async def run_confirm_generation(
    plan_id: int,
    household: Household,
    db: DbSession,
) -> WeeklyPlan:
    """Async part of confirm: recipes + shopping list. Runs as background task.

    With pre-generated recipes (recipe_json already set) this needs no LLM
    call and finishes in well under a second.
    """
    plan = db.get(WeeklyPlan, plan_id)
    if not plan:
        raise ValueError(f"Plan {plan_id} not found")

    confirmed = [d for d in plan.dishes if d.dish_status == "confirmed"]

    recipes = await generate_recipes(confirmed, household, db)

    if confirmed and not recipes:
        # Total failure — put the plan back so the user can retry
        for dish in plan.dishes:
            if dish.dish_status in ("confirmed", "rejected"):
                dish.dish_status = "suggestion"
        plan.status = "suggestions_ready"
        db.commit()
        raise RuntimeError(f"Recipe generation produced nothing for plan {plan_id}")

    build_shopping_list(plan, recipes, household, db)
    plan.status = "confirmed"
    db.commit()
    return plan


async def pregenerate_recipes_for_plan(
    plan: WeeklyPlan,
    household: Household,
    db: DbSession,
) -> int:
    """Pre-generate recipes for all open suggestions (Sunday scheduler job).

    Stores each recipe in dish.recipe_json so confirm needs no LLM call.
    Returns the number of recipes generated.
    """
    open_suggestions = [
        d for d in plan.dishes
        if d.dish_status == "suggestion" and not d.recipe_json
    ]
    if not open_suggestions:
        return 0
    recipes = await generate_recipes(open_suggestions, household, db)
    db.commit()
    return len(recipes)


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

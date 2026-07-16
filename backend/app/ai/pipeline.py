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
from itertools import zip_longest

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
    SavedRecipe,
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
from ..services.status_webhook import report_incident

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Step 1: Filter offers
# ---------------------------------------------------------------------------

def _get_active_offers(plz: str, stores: list[str], db: DbSession) -> list[Offer]:
    """Return cooking-relevant offers from the most recent active brochure per store.

    Stores are interleaved round-robin so no single big brochure (Rewe: 145
    offers) dominates the top of the prompt — the full list goes to the LLM
    (format_offers is uncapped), but a fair mix keeps every store visible
    where model attention is strongest.
    """
    per_store: list[list[Offer]] = []
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
        per_store.append([o for o in brochure.offers if o.is_cooking_relevant])

    result: list[Offer] = []
    for group in zip_longest(*per_store):
        result.extend(o for o in group if o is not None)
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
    profile_text = format_profile(profile, plan.portion_override)
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
        wish_text=plan.wish_text,
    )

    # Budget is deliberately huge: free models cost nothing, and reasoning
    # models with high variance get truncated mid-reasoning by tight limits
    raw, model, usage = await chat_completion_json(
        messages, purpose="dish_suggestions", temperature=0.9, max_tokens=16000,
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


def _format_quantity(qty: float) -> str:
    """Render a rounded quantity for display — decimals kept, trailing zeros dropped.

    0.5 -> "0.5", 1.5 -> "1.5", 250.0 -> "250" (never "250.0").
    """
    if qty == int(qty):
        return str(int(qty))
    return f"{qty:.3f}".rstrip("0").rstrip(".")


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
    portion_override = dish.plan.portion_override if dish.plan else None
    profile_text = format_profile(profile, portion_override)

    messages = build_recipe_prompt(
        dish_name=dish.name,
        dish_description=dish.description or "",
        profile_text=profile_text,
        offers_text=offers_text,
    )

    raw, model, usage = await chat_completion_json(messages, purpose="recipe_gen", max_tokens=8000)
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

    # All dishes in one batch call belong to the same plan (see generate_recipes callers)
    portion_override = dishes[0].plan.portion_override if dishes and dishes[0].plan else None

    messages = build_recipes_batch_prompt(
        dishes=[(d.name, d.description or "") for d in dishes],
        profile_text=format_profile(profile, portion_override),
        offers_text=format_offers(offers),
    )

    # ~1200 tokens per recipe JSON + generous headroom for reasoning models —
    # a too-tight limit truncates the JSON and wastes the whole batch call
    raw, model, usage = await chat_completion_json(
        messages, purpose="recipe_batch", max_tokens=2000 * len(dishes) + 6000,
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
        total = entry["total"]
        if total > 0:
            qty = _format_quantity(_round_quantity(total, entry["unit"]))
        else:
            # Nothing was ever aggregated (e.g. "Salz" with no menge in any
            # recipe) — no quantity to show, as opposed to a genuine small
            # amount that rounds down but is still present.
            qty = None

        store: str | None = None
        offer_id: int | None = None
        price_text: str | None = None

        if entry["is_angebot"] and entry["laden"]:
            store = _normalize_store(entry["laden"])

        # Match every ingredient against currently active offers — not just the
        # ones the LLM flagged ist_angebot at generation time. This is what
        # gives imported/older/manually-entered recipes up-to-date offer
        # pricing when they're planned into a week (task 5).
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


def archive_recipes_to_cookbook(plan: WeeklyPlan, db: DbSession) -> int:
    """Upsert every confirmed dish with a recipe on `plan` into saved_recipes
    (origin="gekocht") so it survives the plan being deleted later.

    Skips dishes whose name (case-insensitive) is already saved for this
    household — idempotent, safe to call repeatedly (e.g. confirm, then
    swap, then regenerate on the same plan). Never raises: a cookbook
    archiving failure must never break the plan flow that calls it.
    Returns the number of rows inserted (0 on failure).
    """
    try:
        household_id = plan.household_id
        existing_names = {
            (name or "").strip().lower()
            for (name,) in db.execute(
                select(SavedRecipe.name).where(SavedRecipe.household_id == household_id)
            ).all()
        }
        added = 0
        for dish in plan.dishes:
            if dish.dish_status != "confirmed" or not dish.recipe_json:
                continue
            key = dish.name.strip().lower()
            if not key or key in existing_names:
                continue
            existing_names.add(key)
            db.add(SavedRecipe(
                household_id=household_id,
                name=dish.name,
                cuisine=dish.cuisine,
                cook_time_min=dish.cook_time_min,
                is_favorite=dish.is_favorite,
                image_url=dish.image_url or (dish.recipe.image_url if dish.recipe else None),
                recipe_json=dish.recipe_json,
                origin="gekocht",
            ))
            added += 1
        db.flush()
        return added
    except Exception:
        logger.warning("archive_recipes_to_cookbook failed for plan %d", plan.id, exc_info=True)
        return 0


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

    # Best-effort dish photos — a no-op without PEXELS_API_KEY, and any failure
    # here must never break suggestion generation itself.
    try:
        from ..services.dish_images import find_dish_image

        for dish in saved:
            dish.image_url = await find_dish_image(dish.name, dish.cuisine)
    except Exception as exc:
        logger.warning("Dish image lookup failed for plan %d: %s", plan.id, exc)

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
    archive_recipes_to_cookbook(plan, db)
    db.commit()

    # Partial failure: some confirmed dishes never got a recipe (e.g. every
    # free-tier model 429'd on that particular batch/individual call). The
    # plan is still confirmed as usual — the user can retry per-dish via
    # regenerate-recipe — but this is worth a status-dashboard incident.
    missing = [d.name for d in confirmed if not d.recipe_json]
    if missing:
        await report_incident(
            f"Teilausfall bei Rezept-Generierung (Plan {plan.id}): "
            f"{len(missing)} Gericht(e) ohne Rezept: {', '.join(missing)}"
        )

    return plan


def _all_confirmed_recipes(
    plan: WeeklyPlan,
    overrides: dict[int, RecipeResponse],
) -> dict[int, RecipeResponse]:
    """Recipes for every currently-confirmed dish: `overrides` wins where given,
    otherwise fall back to each dish's stored recipe_json. Used to assemble the
    full recipe set a shopping-list rebuild needs after only one dish changed."""
    result: dict[int, RecipeResponse] = {}
    for d in plan.dishes:
        if d.dish_status != "confirmed":
            continue
        if d.id in overrides:
            result[d.id] = overrides[d.id]
            continue
        stored = _recipe_from_stored_json(d)
        if stored:
            result[d.id] = stored
    return result


def rebuild_shopping_list_preserving(
    plan: WeeklyPlan,
    recipes: dict[int, RecipeResponse],
    household: Household,
    db: DbSession,
) -> list[ShoppingItem]:
    """Replace plan.shopping_items with a fresh aggregation from `recipes`
    (recipes for ALL currently-confirmed dishes — see _all_confirmed_recipes),
    carrying over is_checked/is_already_have by ingredient name (lowercase)
    and keeping custom (non-offer) items that don't reappear in the new
    aggregation. Shared by run_swap_dish and run_regenerate_recipe.
    """
    old_items = list(plan.shopping_items)
    old_state = {
        i.ingredient.strip().lower(): (i.is_checked, i.is_already_have)
        for i in old_items
    }
    custom_items = [i for i in old_items if i.offer_id is None]

    for item in old_items:
        db.delete(item)
    db.flush()

    new_items = build_shopping_list(plan, recipes, household, db)
    new_names = {i.ingredient.strip().lower() for i in new_items}
    for item in new_items:
        state = old_state.get(item.ingredient.strip().lower())
        if state:
            item.is_checked, item.is_already_have = state

    # Custom items the user added by hand — keep them if the new aggregation
    # didn't happen to produce the same ingredient again.
    for custom in custom_items:
        key = custom.ingredient.strip().lower()
        if key not in new_names:
            db.add(ShoppingItem(
                plan_id=plan.id,
                ingredient=custom.ingredient,
                quantity=custom.quantity,
                unit=custom.unit,
                store=None,
                offer_id=None,
                price_text=None,
                is_checked=custom.is_checked,
                is_already_have=custom.is_already_have,
            ))

    db.flush()
    return new_items


async def run_swap_dish(
    plan_id: int,
    dish_id: int,
    household: Household,
    db: DbSession,
) -> WeeklyPlan:
    """Swap one confirmed dish for a freshly generated one. Runs as background task.

    Rejects the old dish, generates exactly one new confirmed dish on the same
    cook_day, generates its recipe, and rebuilds the shopping list from the
    recipes of all currently-confirmed dishes (reusing stored recipe_json for
    everyone but the new dish). is_checked/is_already_have are carried over by
    ingredient name (lowercase); custom items (no offer_id) that don't reappear
    in the new aggregation are kept as-is.

    On any failure the transaction is rolled back and the plan/old dish are
    explicitly restored — the plan must never be left broken.
    """
    plan = db.get(WeeklyPlan, plan_id)
    if not plan:
        raise ValueError(f"Plan {plan_id} not found")
    old_dish = db.get(PlanDish, dish_id)
    if not old_dish or old_dish.plan_id != plan_id:
        raise ValueError(f"Dish {dish_id} not found on plan {plan_id}")

    cook_day = old_dish.cook_day
    existing_names = [d.name for d in plan.dishes]
    new_dish_id: int | None = None

    try:
        suggestions = await generate_suggestions(
            household=household,
            plan=plan,
            db=db,
            count=1,
            exclude_names=existing_names,
            max_desserts=1,
        )
        if not suggestions:
            raise RuntimeError("Kein neuer Gerichtsvorschlag generiert")
        s = suggestions[0]

        old_dish.dish_status = "rejected"

        new_dish = PlanDish(
            plan_id=plan.id,
            name=s["name"],
            description=s["beschreibung"],
            cuisine=s.get("kategorie"),
            cook_time_min=s.get("kochzeit_min", 30),
            cook_day=cook_day,
            dish_status="confirmed",
            used_offer_ids_json="[]",
            recipe_id=s.get("recipe_id"),
        )
        db.add(new_dish)
        db.flush()
        new_dish_id = new_dish.id

        recipes = await generate_recipes([new_dish], household, db)
        if new_dish.id not in recipes:
            raise RuntimeError(f"Rezept-Generierung für '{new_dish.name}' fehlgeschlagen")

        # Recipes for the shopping list rebuild: new dish's fresh recipe +
        # stored recipe_json for every other currently-confirmed dish.
        all_recipes = _all_confirmed_recipes(plan, {new_dish.id: recipes[new_dish.id]})
        rebuild_shopping_list_preserving(plan, all_recipes, household, db)

        plan.status = "confirmed"
        archive_recipes_to_cookbook(plan, db)
        db.commit()
        return plan

    except Exception:
        db.rollback()
        plan = db.get(WeeklyPlan, plan_id)
        old_dish = db.get(PlanDish, dish_id)
        if old_dish:
            old_dish.dish_status = "confirmed"
        if new_dish_id is not None:
            leftover = db.get(PlanDish, new_dish_id)
            if leftover:
                db.delete(leftover)
        if plan:
            plan.status = "confirmed"
        db.commit()
        raise


async def run_regenerate_recipe(
    plan_id: int,
    dish_id: int,
    household: Household,
    db: DbSession,
    original_status: str = "confirmed",
) -> WeeklyPlan:
    """Retry recipe generation for one confirmed dish that ended up without a
    recipe (all free-tier attempts 429'd during confirm/pregeneration). Runs
    as a background task; the plan status is expected to already be
    'confirming' (set synchronously by the endpoint) and is restored to
    `original_status` on both success and failure.
    """
    plan = db.get(WeeklyPlan, plan_id)
    if not plan:
        raise ValueError(f"Plan {plan_id} not found")
    dish = db.get(PlanDish, dish_id)
    if not dish or dish.plan_id != plan_id:
        raise ValueError(f"Dish {dish_id} not found on plan {plan_id}")

    try:
        recipe = await _llm_recipe(dish, household, db)
        if recipe is None:
            raise RuntimeError(f"Rezept-Generierung für '{dish.name}' fehlgeschlagen")

        dish.recipe_json = recipe.model_dump_json()
        db.flush()

        all_recipes = _all_confirmed_recipes(plan, {dish.id: recipe})
        rebuild_shopping_list_preserving(plan, all_recipes, household, db)

        plan.status = original_status
        archive_recipes_to_cookbook(plan, db)
        db.commit()
        return plan

    except Exception:
        db.rollback()
        plan = db.get(WeeklyPlan, plan_id)
        if plan:
            plan.status = original_status
            db.commit()
        raise


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
            cost_estimate=usage.get("cost") or 0,
        ))
        db.flush()
    except Exception as exc:
        logger.warning("Failed to log api call: %s", exc)

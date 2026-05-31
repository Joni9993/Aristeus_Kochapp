"""Deterministic recipe matching — no LLM, no async.

Entry point:
    suggest_dishes(*, household, plan, db, count=10, exclude_recipe_ids=None)
    → list of (Recipe, score, matched_offer_ids)

Scoring weights:
    Angebots-Treffer (is_main only)  up to budget_sensitivity * 12  (~60 pts max)
    Lieblingsrezept in loved_dishes  +30
    Bevorzugte Küche                 +20
    Gutes Rating (≥4.5, ≥50 votes)   +5
    Kürzlich gekocht/confirmed (≤4 Wochen)  -25
    Kürzlich vorgeschlagen (letzte 2 Pläne) -15
    Cuisine-Duplikat in Top-N               -15  (greedy, applied during selection)
    Zufalls-Tiebreaker                      ±3   (rotation between plans)
"""

import json
import logging
import random
from dataclasses import dataclass, field
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from ..models import (
    LearnedPreferences,
    Offer,
    PlanDish,
    Recipe,
    RecipeIngredient,
    WeeklyPlan,
)

logger = logging.getLogger(__name__)

# Minimum fraction of ingredients that must match active offers per budget_sensitivity level.
# Acts as a hard filter; at sensitivity=1 only 10% need to match (very inclusive).
_OFFER_MIN_PERCENT = {1: 0.10, 2: 0.20, 3: 0.30, 4: 0.40, 5: 0.50}
# If fewer than this many recipes pass the offer filter, relax by one sensitivity level.
_OFFER_MIN_POOL = 20


@dataclass
class ScoredRecipe:
    recipe: Recipe
    score: float
    matched_offer_ids: list[int] = field(default_factory=list)
    match_reasons: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Offer matching (reused logic, operates on normalized_name)
# ---------------------------------------------------------------------------

def find_matching_offer(normalized_name: str, offers: list[Offer]) -> Offer | None:
    """Return the best-matching active offer for a normalized ingredient name."""
    if not normalized_name:
        return None
    name_lower = normalized_name.lower()
    # Exact
    for o in offers:
        if o.product_name.lower() == name_lower:
            return o
    # Substring
    for o in offers:
        offer_lower = o.product_name.lower()
        if name_lower in offer_lower or offer_lower in name_lower:
            return o
    # Word overlap (2+ meaningful words)
    name_words = {w for w in name_lower.split() if len(w) > 3}
    if name_words:
        for o in offers:
            offer_words = {w for w in o.product_name.lower().split() if len(w) > 3}
            if len(name_words & offer_words) >= 2:
                return o
    return None


# ---------------------------------------------------------------------------
# Hard filter helpers
# ---------------------------------------------------------------------------

def _passes_diet(recipe: Recipe, diet: str, allowed_meats: list[str]) -> bool:
    diet = diet.lower()
    if diet == "vegan":
        return recipe.is_vegan
    if diet in ("vegetarian", "vegetarisch"):
        return recipe.is_vegetarian
    # omnivore / flexitarian: check allowed meats
    meat_kinds: list[str] = json.loads(recipe.meat_kinds_json or "[]")
    if not meat_kinds:
        return True  # no meat at all — always fine
    # Dish contains meat — every meat kind must be in allowed list
    return all(mk in allowed_meats for mk in meat_kinds)


def _passes_allergies(recipe: Recipe, allergies: list[str], no_gos: list[str]) -> bool:
    allergens: list[str] = json.loads(recipe.allergen_flags_json or "[]")
    for a in allergies:
        if a.lower() in allergens:
            return False
    # No-go check against recipe name (simple)
    name_lower = recipe.name.lower()
    for ng in no_gos:
        if ng.lower() in name_lower:
            return False
    return True


def _passes_cooktime(recipe: Recipe, max_min: int) -> bool:
    if recipe.cook_time_min is None:
        return True  # unknown cook time — allow
    return recipe.cook_time_min <= max_min


# ---------------------------------------------------------------------------
# Recent history helpers
# ---------------------------------------------------------------------------

def _recently_cooked_recipe_ids(household_id: int, weeks: int, db: DbSession) -> set[int]:
    cutoff = (date.today() - timedelta(weeks=weeks)).isoformat()
    dishes = db.scalars(
        select(PlanDish)
        .join(WeeklyPlan)
        .where(
            WeeklyPlan.household_id == household_id,
            WeeklyPlan.week_start_date >= cutoff,
            PlanDish.dish_status == "confirmed",
            PlanDish.recipe_id.isnot(None),
        )
    ).all()
    return {d.recipe_id for d in dishes}


def _recently_suggested_per_plan(
    household_id: int, current_plan_id: int, plan_count: int, db: DbSession
) -> list[set[int]]:
    """Returns [last_plan_ids, second_last_ids, ...] — one set per recent plan, newest first."""
    recent_plans = db.scalars(
        select(WeeklyPlan)
        .where(
            WeeklyPlan.household_id == household_id,
            WeeklyPlan.id != current_plan_id,
        )
        .order_by(WeeklyPlan.id.desc())
        .limit(plan_count)
    ).all()
    return [
        {d.recipe_id for d in plan.dishes if d.recipe_id is not None}
        for plan in recent_plans
    ]


def _loved_recipe_names(household_id: int, db: DbSession) -> set[str]:
    prefs = db.scalar(
        select(LearnedPreferences).where(LearnedPreferences.household_id == household_id)
    )
    if not prefs:
        return set()
    loved: list[str] = json.loads(prefs.loved_dishes_json or "[]")
    return {n.lower() for n in loved}


def _disliked_recipe_names(household_id: int, db: DbSession) -> set[str]:
    prefs = db.scalar(
        select(LearnedPreferences).where(LearnedPreferences.household_id == household_id)
    )
    if not prefs:
        return set()
    disliked: list[str] = json.loads(prefs.disliked_dishes_json or "[]")
    return {n.lower() for n in disliked}


# ---------------------------------------------------------------------------
# Main suggest function
# ---------------------------------------------------------------------------

def suggest_dishes(
    *,
    household,
    plan: WeeklyPlan,
    db: DbSession,
    count: int = 10,
    exclude_recipe_ids: list[int] | None = None,
    max_desserts: int = 2,
) -> list[ScoredRecipe]:
    from ..ai.pipeline import _get_active_offers  # avoid circular at module level

    profile = household.profile
    diet = profile.diet or "omnivore"
    allowed_meats: list[str] = json.loads(profile.allowed_meats_json or "[]")
    allergies: list[str] = json.loads(profile.allergies_json or "[]")
    no_gos: list[str] = json.loads(profile.no_gos_json or "[]")
    preferred_cuisines: list[str] = [
        c.lower() for c in json.loads(profile.preferred_cuisines_json or "[]")
    ]
    budget_sensitivity: int = profile.budget_sensitivity or 3
    max_cook_time: int = profile.max_cook_time_min or 60

    # Active offers for matching
    stores: list[str] = json.loads(profile.selected_stores_json or "[]")
    active_offers = _get_active_offers(profile.postal_code or "", stores, db)

    # History / preferences
    recently_cooked = _recently_cooked_recipe_ids(household.id, weeks=4, db=db)
    # [0] = last plan (hard-excluded), [1] = second-last plan (soft penalty)
    suggested_per_plan = _recently_suggested_per_plan(household.id, plan.id, plan_count=2, db=db)
    last_plan_ids = suggested_per_plan[0] if len(suggested_per_plan) > 0 else set()
    prev_plan_ids = suggested_per_plan[1] if len(suggested_per_plan) > 1 else set()
    loved_names = _loved_recipe_names(household.id, db)
    disliked_names = _disliked_recipe_names(household.id, db)

    excluded_ids: set[int] = set(exclude_recipe_ids or []) | last_plan_ids

    include_desserts: bool = getattr(profile, "include_desserts", False)

    # 1) Fetch candidate pool — hard filter via SQL where possible
    query = select(Recipe)
    if diet == "vegan":
        query = query.where(Recipe.is_vegan == True)  # noqa: E712
    elif diet in ("vegetarian", "vegetarisch"):
        query = query.where(Recipe.is_vegetarian == True)  # noqa: E712
    # cook time
    query = query.where(
        (Recipe.cook_time_min == None) | (Recipe.cook_time_min <= max_cook_time)  # noqa: E711
    )
    # meal type filter: always exclude drinks/Grundrezepte; desserts optional
    if include_desserts:
        query = query.where(Recipe.meal_type.in_(["hauptgericht", "dessert"]))
    else:
        query = query.where(Recipe.meal_type == "hauptgericht")

    candidates: list[Recipe] = list(db.scalars(query).all())

    # 2) Python-side hard filters (meat, allergies, no-gos, excluded ids, disliked)
    filtered: list[Recipe] = []
    for r in candidates:
        if r.id in excluded_ids:
            continue
        if r.name.lower() in disliked_names:
            continue
        if not _passes_diet(r, diet, allowed_meats):
            continue
        if not _passes_allergies(r, allergies, no_gos):
            continue
        filtered.append(r)

    logger.info(
        "Matcher: %d candidates → %d after hard filter (plan %d)",
        len(candidates), len(filtered), plan.id,
    )

    if not filtered:
        return []

    # 3) Offer percentage filter — load ALL ingredients once, compute hit rate per recipe
    recipe_ids = [r.id for r in filtered]
    all_ings: list[RecipeIngredient] = list(db.scalars(
        select(RecipeIngredient)
        .where(RecipeIngredient.recipe_id.in_(recipe_ids))
    ).all())

    ings_by_recipe: dict[int, list[RecipeIngredient]] = {}
    for ing in all_ings:
        ings_by_recipe.setdefault(ing.recipe_id, []).append(ing)

    # Pre-compute offer matches per recipe (reused in scoring for match_reasons)
    offer_match_ids: dict[int, list[int]] = {}
    pct_by_recipe: dict[int, float] = {}
    for recipe in filtered:
        ings = ings_by_recipe.get(recipe.id, [])
        if not ings:
            pct_by_recipe[recipe.id] = 0.0
            offer_match_ids[recipe.id] = []
            continue
        hit_ids: list[int] = []
        for ing in ings:
            offer = find_matching_offer(ing.normalized_name, active_offers)
            if offer:
                hit_ids.append(offer.id)
        pct_by_recipe[recipe.id] = len(hit_ids) / len(ings)
        offer_match_ids[recipe.id] = hit_ids

    min_pct = _OFFER_MIN_PERCENT.get(budget_sensitivity, 0.30)
    offer_filtered = [r for r in filtered if pct_by_recipe.get(r.id, 0.0) >= min_pct]

    # Fallback: if pool too small, relax by one sensitivity step
    if len(offer_filtered) < _OFFER_MIN_POOL and budget_sensitivity > 1:
        relaxed_pct = _OFFER_MIN_PERCENT.get(budget_sensitivity - 1, 0.10)
        logger.info(
            "Offer filter pool too small (%d < %d) at %.0f%% — relaxing to %.0f%%",
            len(offer_filtered), _OFFER_MIN_POOL, min_pct * 100, relaxed_pct * 100,
        )
        offer_filtered = [r for r in filtered if pct_by_recipe.get(r.id, 0.0) >= relaxed_pct]

    filtered = offer_filtered

    logger.info(
        "Matcher: %d after offer filter (budget_sensitivity=%d, min=%.0f%%)",
        len(filtered), budget_sensitivity, min_pct * 100,
    )

    if not filtered:
        return []

    scored: list[ScoredRecipe] = []
    for recipe in filtered:
        score = 0.0
        reasons: list[str] = []
        matched_offer_ids: list[int] = offer_match_ids.get(recipe.id, [])

        # Offer match info — already used as hard filter above, shown as reason only
        total_ings = len(ings_by_recipe.get(recipe.id, []))
        if matched_offer_ids and total_ings:
            reasons.append(f"{len(matched_offer_ids)}/{total_ings} Zutaten im Angebot")

        # Loved dish
        if recipe.name.lower() in loved_names:
            score += 30
            reasons.append("geliebt")

        # Preferred cuisine
        if recipe.cuisine and recipe.cuisine.lower() in preferred_cuisines:
            score += 20
            reasons.append("Lieblingsküche")

        # Good rating
        if recipe.rating_avg and recipe.rating_avg >= 4.5 and (recipe.rating_count or 0) >= 50:
            score += 5
            reasons.append("top Bewertung")

        # Recently cooked (confirmed) — strong penalty
        if recipe.id in recently_cooked:
            score -= 25

        # Suggested in the plan before last — soft penalty
        if recipe.id in prev_plan_ids:
            score -= 20

        # Small random tiebreaker so equal-score recipes rotate between plans
        score += random.uniform(-3, 3)

        scored.append(ScoredRecipe(
            recipe=recipe,
            score=score,
            matched_offer_ids=matched_offer_ids,
            match_reasons=reasons,
        ))

    # 4) Greedy Top-N with cuisine + dessert diversity constraints
    scored.sort(key=lambda s: s.score, reverse=True)

    MAX_DESSERTS = max_desserts if include_desserts else 0

    cuisine_counts: dict[str, int] = {}
    dessert_count = 0
    deferred: list[ScoredRecipe] = []
    result: list[ScoredRecipe] = []

    for sr in scored:
        if len(result) >= count:
            break
        is_dessert = sr.recipe.meal_type == "dessert"
        cuisine = (sr.recipe.cuisine or "sonstige").lower()

        if is_dessert and dessert_count >= MAX_DESSERTS:
            deferred.append(sr)
            continue
        if not is_dessert and cuisine_counts.get(cuisine, 0) >= 2:
            deferred.append(sr)
            continue

        if is_dessert:
            dessert_count += 1
        else:
            cuisine_counts[cuisine] = cuisine_counts.get(cuisine, 0) + 1
        result.append(sr)

    # Fill remaining slots from deferred entries (cuisine- or dessert-capped)
    if len(result) < count:
        added_ids = {sr.recipe.id for sr in result}
        for sr in deferred + [s for s in scored if s.recipe.id not in added_ids]:
            if len(result) >= count:
                break
            if sr.recipe.id not in added_ids:
                result.append(sr)
                added_ids.add(sr.recipe.id)

    # Always place desserts at the end of the list
    result.sort(key=lambda sr: 1 if sr.recipe.meal_type == "dessert" else 0)

    logger.info("Matcher: returning %d suggestions for plan %d", len(result), plan.id)
    return result

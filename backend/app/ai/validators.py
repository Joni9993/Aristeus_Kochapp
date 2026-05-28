"""Deterministic post-validators for LLM dish suggestions."""

import json
import logging

from ..models import Profile
from .schemas import DishSuggestion

logger = logging.getLogger(__name__)

# Keyword → diet flags that would block the dish
_MEAT_KEYWORDS: dict[str, list[str]] = {
    "chicken": ["hähnchen", "huhn", "hühnchen", "chicken"],
    "turkey": ["pute", "truthahn", "turkey"],
    "beef": ["rind", "beef", "steak", "hackfleisch"],
    "pork": ["schwein", "pork", "speck", "bacon", "wurst", "schinken"],
    "fish": ["fisch", "lachs", "thunfisch", "forelle", "garnele", "shrimp", "meeresfrüchte"],
}

_VEGAN_BLOCKED = ["ei ", "eier", "milch", "käse", "butter", "sahne", "joghurt",
                  "quark", "honig", "fleisch", "fisch", "lachs", "wurst"]
_VEGETARIAN_BLOCKED = ["fleisch", "hackfleisch", "hähnchen", "huhn", "rind",
                       "schwein", "wurst", "speck", "thunfisch", "lachs",
                       "garnele", "pute", "truthahn"]


def _text_of(dish: DishSuggestion) -> str:
    return (dish.name + " " + dish.beschreibung + " " + " ".join(dish.hauptzutaten)).lower()


def passes_diet(dish: DishSuggestion, profile: Profile) -> bool:
    text = _text_of(dish)
    diet = profile.diet.lower()

    if diet == "vegan":
        for kw in _VEGAN_BLOCKED:
            if kw in text:
                return False

    elif diet == "vegetarian" or diet == "vegetarisch":
        for kw in _VEGETARIAN_BLOCKED:
            if kw in text:
                return False

    elif diet in ("omnivore", "flexitarian", "flexitarisch"):
        allowed: list[str] = json.loads(profile.allowed_meats_json or "[]")
        for meat_key, kws in _MEAT_KEYWORDS.items():
            if meat_key not in allowed:
                for kw in kws:
                    if kw in text:
                        return False

    return True


def passes_allergies(dish: DishSuggestion, profile: Profile) -> bool:
    allergies: list[str] = json.loads(profile.allergies_json or "[]")
    no_gos: list[str] = json.loads(profile.no_gos_json or "[]")
    text = _text_of(dish)
    for item in allergies + no_gos:
        if item.lower() in text:
            logger.debug("Dish '%s' blocked: contains allergen/no-go '%s'", dish.name, item)
            return False
    return True


def passes_cooktime(dish: DishSuggestion, profile: Profile) -> bool:
    return dish.kochzeit_min <= profile.max_cook_time_min


def validate_suggestions(
    dishes: list[DishSuggestion],
    profile: Profile,
) -> list[DishSuggestion]:
    """Filter suggestions that violate profile constraints. Deduplicate by name."""
    seen_names: set[str] = set()
    valid: list[DishSuggestion] = []

    for dish in dishes:
        norm = dish.name.strip().lower()
        if norm in seen_names:
            continue
        seen_names.add(norm)

        if not passes_diet(dish, profile):
            logger.debug("Dish '%s' removed: diet constraint (%s)", dish.name, profile.diet)
            continue
        if not passes_allergies(dish, profile):
            continue
        if not passes_cooktime(dish, profile):
            logger.debug("Dish '%s' removed: cook time %d > %d", dish.name, dish.kochzeit_min, profile.max_cook_time_min)
            continue

        valid.append(dish)

    return valid

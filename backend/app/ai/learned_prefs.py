"""Build learning context from stored preferences for prompt injection."""

import json
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from ..models import LearnedPreferences, PlanDish, WeeklyPlan

logger = logging.getLogger(__name__)


def get_or_create(household_id: int, db: DbSession) -> LearnedPreferences:
    prefs = db.scalar(
        select(LearnedPreferences).where(LearnedPreferences.household_id == household_id)
    )
    if not prefs:
        prefs = LearnedPreferences(
            household_id=household_id,
            loved_dishes_json="[]",
            disliked_dishes_json="[]",
            portion_adjustments_json="{}",
        )
        db.add(prefs)
        db.flush()
    return prefs


def build_learn_context(household_id: int, db: DbSession) -> str:
    """Return a short human-readable context string for the prompt."""
    prefs = db.scalar(
        select(LearnedPreferences).where(LearnedPreferences.household_id == household_id)
    )
    if not prefs:
        return ""

    loved: list[str] = json.loads(prefs.loved_dishes_json or "[]")
    disliked: list[str] = json.loads(prefs.disliked_dishes_json or "[]")
    notes = prefs.recurring_notes or ""

    parts: list[str] = []
    if loved:
        parts.append(f"Sehr beliebt: {', '.join(loved[:5])}")
    if disliked:
        parts.append(f"Nicht gemocht: {', '.join(disliked[:5])}")
    if notes:
        parts.append(f"Notizen: {notes}")

    return "\n".join(parts)


def update_from_feedback(household_id: int, db: DbSession) -> None:
    """Aggregate feedback from all completed plans into learned_preferences."""
    prefs = get_or_create(household_id, db)

    # Collect all dishes with thumbs feedback
    dishes = db.scalars(
        select(PlanDish)
        .join(WeeklyPlan)
        .where(
            WeeklyPlan.household_id == household_id,
            PlanDish.feedback_thumbs.isnot(None),
        )
    ).all()

    loved_counts: dict[str, int] = {}
    disliked_counts: dict[str, int] = {}

    for d in dishes:
        key = d.name.strip()
        if d.feedback_thumbs == 1:
            loved_counts[key] = loved_counts.get(key, 0) + 1
        elif d.feedback_thumbs == -1:
            disliked_counts[key] = disliked_counts.get(key, 0) + 1

    # Top 10 most loved / disliked
    loved = sorted(loved_counts.keys(), key=lambda k: -loved_counts[k])[:10]
    disliked = sorted(disliked_counts.keys(), key=lambda k: -disliked_counts[k])[:10]

    prefs.loved_dishes_json = json.dumps(loved, ensure_ascii=False)
    prefs.disliked_dishes_json = json.dumps(disliked, ensure_ascii=False)
    db.commit()
    logger.info("Updated learned_preferences for household %d", household_id)

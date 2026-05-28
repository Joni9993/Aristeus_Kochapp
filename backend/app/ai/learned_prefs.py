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
    adjustments: dict[str, str] = json.loads(prefs.portion_adjustments_json or "{}")
    notes = prefs.recurring_notes or ""

    parts: list[str] = []
    if loved:
        parts.append(f"Sehr beliebt: {', '.join(loved[:5])}")
    if disliked:
        parts.append(f"Nicht gemocht: {', '.join(disliked[:5])}")
    if adjustments:
        adj_text = "; ".join(f"{k}: {v}" for k, v in list(adjustments.items())[:5])
        parts.append(f"Portionen anpassen: {adj_text}")
    if notes:
        parts.append(f"Notizen: {notes}")

    return "\n".join(parts)


def update_from_feedback(household_id: int, db: DbSession) -> None:
    """Aggregate thumbs + portion feedback from all plans into learned_preferences."""
    prefs = get_or_create(household_id, db)

    # Thumbs aggregation
    dishes_thumbs = db.scalars(
        select(PlanDish)
        .join(WeeklyPlan)
        .where(
            WeeklyPlan.household_id == household_id,
            PlanDish.feedback_thumbs.isnot(None),
        )
    ).all()

    loved_counts: dict[str, int] = {}
    disliked_counts: dict[str, int] = {}
    for d in dishes_thumbs:
        key = d.name.strip()
        if d.feedback_thumbs == 1:
            loved_counts[key] = loved_counts.get(key, 0) + 1
        elif d.feedback_thumbs == -1:
            disliked_counts[key] = disliked_counts.get(key, 0) + 1

    loved = sorted(loved_counts.keys(), key=lambda k: -loved_counts[k])[:10]
    disliked = sorted(disliked_counts.keys(), key=lambda k: -disliked_counts[k])[:10]
    prefs.loved_dishes_json = json.dumps(loved, ensure_ascii=False)
    prefs.disliked_dishes_json = json.dumps(disliked, ensure_ascii=False)

    # Portion aggregation — only flag if 2+ consistent reports
    dishes_portion = db.scalars(
        select(PlanDish)
        .join(WeeklyPlan)
        .where(
            WeeklyPlan.household_id == household_id,
            PlanDish.feedback_portion_note.isnot(None),
        )
    ).all()

    too_much: dict[str, int] = {}
    too_little: dict[str, int] = {}
    for d in dishes_portion:
        key = d.name.strip()
        if d.feedback_portion_note == "zu viel":
            too_much[key] = too_much.get(key, 0) + 1
        elif d.feedback_portion_note == "zu wenig":
            too_little[key] = too_little.get(key, 0) + 1

    adjustments: dict[str, str] = {}
    for name, count in too_much.items():
        if count >= 2:
            adjustments[name] = "oft zu viel"
    for name, count in too_little.items():
        if count >= 2:
            adjustments[name] = "oft zu wenig"

    prefs.portion_adjustments_json = json.dumps(adjustments, ensure_ascii=False)
    db.commit()
    logger.info("Updated learned_preferences for household %d", household_id)


async def aggregate_notes_with_llm(household_id: int, db: DbSession) -> None:
    """Extract preference patterns from free-text feedback via LLM → recurring_notes."""
    from .client import chat_completion_json
    from .prompts import build_feedback_summary_prompt

    prefs = get_or_create(household_id, db)

    dishes = db.scalars(
        select(PlanDish)
        .join(WeeklyPlan)
        .where(
            WeeklyPlan.household_id == household_id,
            (PlanDish.feedback_thumbs.isnot(None)) | (PlanDish.feedback_free_text.isnot(None)),
        )
    ).all()

    if not dishes:
        return

    entries = [
        {
            "name": d.name,
            "thumbs": d.feedback_thumbs,
            "portion_note": d.feedback_portion_note,
            "free_text": d.feedback_free_text or "",
        }
        for d in dishes
    ]

    try:
        messages = build_feedback_summary_prompt(entries)
        data, _, _ = await chat_completion_json(messages, purpose="feedback_summary")
        muster: list[str] = data.get("muster", [])
        empfehlungen: list[str] = data.get("empfehlungen", [])

        parts: list[str] = []
        if muster:
            parts.append("Muster: " + "; ".join(muster))
        if empfehlungen:
            parts.append("Empfehlungen: " + "; ".join(empfehlungen))

        prefs.recurring_notes = "\n".join(parts) if parts else None
        db.commit()
        logger.info("Updated recurring_notes for household %d via LLM", household_id)
    except Exception as exc:
        logger.warning("LLM feedback aggregation failed for household %d: %s", household_id, exc)

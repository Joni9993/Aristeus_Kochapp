"""APScheduler nightly Kaufda refresh.

Every night at 03:00 the scheduler finds all unique (plz, stores) combinations
from active profiles and refreshes the offers. One request per PLZ — households
in the same region share the same brochure data.
"""

import asyncio
import json
import logging
from datetime import date, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select

from ..db import SessionLocal
from ..models import Household, Profile, WeeklyPlan
from ..ai.learned_prefs import aggregate_notes_with_llm, update_from_feedback
from .kaufda import refresh_plz
from .status_webhook import report_incident

logger = logging.getLogger(__name__)

# Pre-generation targets: 30 suggestions per household (LLM calls à max 10,
# exclude list accumulates between calls; the validator drops some per call,
# so we loop until the target is reached) + recipes for all of them.
_PREGEN_TOTAL = 30
_PREGEN_BATCH = 10
_PREGEN_MAX_CALLS = 5

scheduler = AsyncIOScheduler(timezone="Europe/Berlin")


async def _run_nightly_refresh() -> None:
    logger.info("Nightly Kaufda refresh started")
    db = SessionLocal()
    try:
        profiles = db.scalars(
            select(Profile).where(Profile.onboarding_complete.is_(True), Profile.postal_code != "")
        ).all()

        # Deduplicate by PLZ — group all selected stores across households in same PLZ
        plz_stores: dict[str, set[str]] = {}
        for p in profiles:
            stores = json.loads(p.selected_stores_json)
            plz = p.postal_code
            plz_stores.setdefault(plz, set()).update(stores)

        for plz, stores in plz_stores.items():
            try:
                summary = await refresh_plz(plz, list(stores), db)
                logger.info("Refresh done for PLZ %s: %s", plz, summary)
            except Exception as exc:
                logger.error("Refresh failed for PLZ %s: %s", plz, exc)
    finally:
        db.close()

    logger.info("Nightly Kaufda refresh finished")


def _run_refresh_sync() -> None:
    asyncio.run(_run_nightly_refresh())


async def _run_aggregation_async() -> None:
    logger.info("Weekly feedback aggregation started")
    db = SessionLocal()
    try:
        household_ids = db.scalars(select(Household.id)).all()
        for hid in household_ids:
            try:
                update_from_feedback(hid, db)
                await aggregate_notes_with_llm(hid, db)
            except Exception as exc:
                logger.error("Aggregation failed for household %d: %s", hid, exc)
    finally:
        db.close()
    logger.info("Weekly feedback aggregation finished")


def _run_weekly_aggregation() -> None:
    asyncio.run(_run_aggregation_async())


def _next_monday() -> str:
    today = date.today()
    days_ahead = (7 - today.weekday()) % 7 or 7  # strictly next Monday
    return (today + timedelta(days=days_ahead)).isoformat()


def _this_monday() -> str:
    today = date.today()
    return (today - timedelta(days=today.weekday())).isoformat()


async def _run_pregeneration_async(week_start: str | None = None, force: bool = False) -> None:
    """Sunday 04:00: pre-generate next week's plan for every onboarded household.

    Creates the plan, generates 30 suggestions and all recipes so that opening
    the app on Sunday/Monday needs zero LLM calls. Households that already have
    a usable plan for that week are skipped (plans in status 'error' don't
    count). week_start/force are for manual runs.
    """
    from ..ai.pipeline import pregenerate_recipes_for_plan, run_suggestions_step

    logger.info("Weekly pre-generation started")
    db = SessionLocal()
    try:
        week_start = week_start or _next_monday()
        households = db.scalars(
            select(Household)
            .join(Profile)
            .where(Profile.onboarding_complete.is_(True), Profile.postal_code != "")
        ).all()

        for household in households:
            try:
                existing = db.scalar(
                    select(WeeklyPlan).where(
                        WeeklyPlan.household_id == household.id,
                        WeeklyPlan.week_start_date == week_start,
                        WeeklyPlan.status != "error",
                    )
                )
                if existing and not force:
                    logger.info(
                        "Pre-generation: household %d already has plan %d for %s — skipped",
                        household.id, existing.id, week_start,
                    )
                    continue

                plan = WeeklyPlan(
                    household_id=household.id,
                    week_start_date=week_start,
                    status="pending",
                )
                db.add(plan)
                db.commit()
                db.refresh(plan)

                for _ in range(_PREGEN_MAX_CALLS):
                    n = len([d for d in plan.dishes if d.dish_status == "suggestion"])
                    if n >= _PREGEN_TOTAL:
                        break
                    await run_suggestions_step(
                        plan.id, household, db,
                        count=min(_PREGEN_BATCH, _PREGEN_TOTAL - n),
                    )
                    db.refresh(plan)

                generated = await pregenerate_recipes_for_plan(plan, household, db)
                logger.info(
                    "Pre-generation: plan %d for household %d — %d suggestions, %d recipes",
                    plan.id, household.id,
                    len([d for d in plan.dishes if d.dish_status == "suggestion"]),
                    generated,
                )
            except Exception as exc:
                logger.error("Pre-generation failed for household %d: %s", household.id, exc, exc_info=True)
                await report_incident(
                    f"Vorgenerierung für Woche {week_start} fehlgeschlagen "
                    f"(Haushalt {household.id}): {exc}"
                )
    finally:
        db.close()
    logger.info("Weekly pre-generation finished")


def _run_pregeneration_sync() -> None:
    asyncio.run(_run_pregeneration_async())


async def _run_healthcheck_async() -> None:
    """Monday 07:00: verify every onboarded household got a plan for the
    current week from the Sunday pre-generation. Never raises — a broken
    healthcheck must not take the scheduler down."""
    logger.info("Pre-generation healthcheck started")
    db = SessionLocal()
    try:
        week_start = _this_monday()
        households = db.scalars(
            select(Household)
            .join(Profile)
            .where(Profile.onboarding_complete.is_(True), Profile.postal_code != "")
        ).all()

        missing: list[int] = []
        for household in households:
            existing = db.scalar(
                select(WeeklyPlan).where(
                    WeeklyPlan.household_id == household.id,
                    WeeklyPlan.week_start_date == week_start,
                    WeeklyPlan.status != "error",
                )
            )
            if not existing:
                missing.append(household.id)

        if missing:
            summary = (
                f"Healthcheck {week_start}: {len(missing)}/{len(households)} "
                f"Haushalt(e) ohne gültigen Plan für die aktuelle Woche: {missing}"
            )
            logger.warning(summary)
            await report_incident(summary)
        else:
            logger.info(
                "Healthcheck %s: all %d households have a plan", week_start, len(households)
            )
    except Exception as exc:
        logger.error("Pre-generation healthcheck failed: %s", exc, exc_info=True)
    finally:
        db.close()
    logger.info("Pre-generation healthcheck finished")


def _run_healthcheck_sync() -> None:
    asyncio.run(_run_healthcheck_async())


def start_scheduler() -> None:
    scheduler.add_job(
        _run_refresh_sync,
        trigger="cron",
        day_of_week="sat",
        hour=3,
        minute=0,
        id="saturday_kaufda_refresh",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    scheduler.add_job(
        _run_refresh_sync,
        trigger="cron",
        day_of_week="sun",
        hour=3,
        minute=0,
        id="sunday_kaufda_refresh",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    scheduler.add_job(
        _run_pregeneration_sync,
        trigger="cron",
        day_of_week="sun",
        hour=4,
        minute=0,
        id="weekly_plan_pregeneration",
        replace_existing=True,
        misfire_grace_time=7200,
    )
    scheduler.add_job(
        _run_weekly_aggregation,
        trigger="cron",
        day_of_week="mon",
        hour=4,
        minute=0,
        id="weekly_feedback_aggregation",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    scheduler.add_job(
        _run_healthcheck_sync,
        trigger="cron",
        day_of_week="mon",
        hour=7,
        minute=0,
        id="monday_pregeneration_healthcheck",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    scheduler.start()
    logger.info(
        "APScheduler started — Kaufda refresh Sa+So 03:00, pre-generation So 04:00, "
        "feedback aggregation Mo 04:00, pre-generation healthcheck Mo 07:00"
    )


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)

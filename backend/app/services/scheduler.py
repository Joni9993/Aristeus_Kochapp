"""APScheduler nightly Kaufda refresh.

Every night at 03:00 the scheduler finds all unique (plz, stores) combinations
from active profiles and refreshes the offers. One request per PLZ — households
in the same region share the same brochure data.
"""

import asyncio
import json
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select

from ..db import SessionLocal
from ..models import Profile
from .kaufda import refresh_plz

logger = logging.getLogger(__name__)

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


def start_scheduler() -> None:
    scheduler.add_job(
        _run_refresh_sync,
        trigger="cron",
        hour=3,
        minute=0,
        id="nightly_kaufda_refresh",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    scheduler.start()
    logger.info("APScheduler started — nightly Kaufda refresh at 03:00")


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)

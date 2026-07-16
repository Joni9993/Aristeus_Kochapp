"""Incident reporting to the self-hosted status dashboard (status.tr4jon.com).

The dashboard's /api/kuma-webhook endpoint accepts Kuma-style payloads and
turns them into an entry in the "Letzte Vorfälle" feed plus a Web Push:

    {"monitor": {"name": ...}, "heartbeat": {"status": 0|1, "msg": ...}}

status 0 = incident ("DOWN"), status 1 = recovery ("UP"). We only send
incidents — weekly success pings would just clutter the feed.

Fire-and-forget: reporting must never break the caller. No-op when
STATUS_WEBHOOK_URL is unset.
"""

import logging

logger = logging.getLogger(__name__)

MONITOR_NAME = "Aristeus Wochenplan"


async def report_incident(msg: str, *, monitor: str = MONITOR_NAME) -> None:
    """POST an incident to the status dashboard. Swallows every error."""
    from ..config import get_settings

    url = get_settings().status_webhook_url
    if not url:
        return
    try:
        import httpx

        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(
                url,
                json={
                    "monitor": {"name": monitor},
                    "heartbeat": {"status": 0, "msg": msg[:500]},
                },
            )
        logger.info("Reported incident to status dashboard: %s", msg[:200])
    except Exception as exc:
        logger.error("Status-webhook POST failed: %s", exc)

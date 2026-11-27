import asyncio
import hashlib
import hmac
import json
import logging
import time
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sentinel_backend.db.session import async_session_maker
from sentinel_backend.models.webhook import WebhookEndpoint

logger = logging.getLogger(__name__)

_RETRY_BACKOFF_SECONDS: tuple[float, ...] = (0.5, 1.5, 3.0)
_MAX_DELIVERY_ATTEMPTS = 3
_background_tasks: set[asyncio.Task[Any]] = set()


def _sign_payload(secret: str, timestamp: int, raw_body: str) -> str:
    """Compute HMAC-SHA256 webhook signature header value."""
    sig = hmac.new(
        secret.encode("utf-8"),
        f"{timestamp}.{raw_body}".encode(),
        hashlib.sha256,
    ).hexdigest()
    return f"t={timestamp},v1={sig}"


async def deliver_single_webhook(
    webhook_id: str,
    url: str,
    secret: str,
    event_type: str,
    payload: dict[str, Any],
) -> int | None:
    """Deliver a signed JSON webhook event with bounded exponential backoff retries."""
    raw_body = json.dumps(
        {
            "event": event_type,
            "timestamp": datetime.now(UTC).isoformat(),
            "data": payload,
        },
        default=str,
    )

    final_status_code: int | None = None

    async with httpx.AsyncClient(timeout=5.0) as client:
        for attempt in range(_MAX_DELIVERY_ATTEMPTS):
            timestamp = int(time.time())
            headers = {
                "Content-Type": "application/json",
                "X-Sentinel-Event": event_type,
                "X-Sentinel-Signature": _sign_payload(secret, timestamp, raw_body),
            }
            should_retry = False
            try:
                response = await client.post(
                    url,
                    content=raw_body,
                    headers=headers,
                )
                final_status_code = response.status_code
                if response.status_code < 500:
                    break
                should_retry = True
                logger.warning(
                    "Webhook %s (%s) returned status %d on attempt %d/%d",
                    webhook_id,
                    event_type,
                    response.status_code,
                    attempt + 1,
                    _MAX_DELIVERY_ATTEMPTS,
                )
            except httpx.HTTPError as exc:
                should_retry = True
                logger.warning(
                    "Webhook %s (%s) delivery error on attempt %d/%d: %s",
                    webhook_id,
                    event_type,
                    attempt + 1,
                    _MAX_DELIVERY_ATTEMPTS,
                    exc,
                )

            if should_retry and attempt < _MAX_DELIVERY_ATTEMPTS - 1:
                await asyncio.sleep(_RETRY_BACKOFF_SECONDS[attempt])

    try:
        async with async_session_maker() as session:
            endpoint = await session.get(WebhookEndpoint, webhook_id)
            if endpoint is not None:
                endpoint.last_status_code = final_status_code
                endpoint.last_triggered_at = datetime.now(UTC)
                await session.commit()
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Failed to record delivery metadata for webhook %s: %s",
            webhook_id,
            exc,
        )

    return final_status_code


async def enqueue_team_webhooks(
    db: AsyncSession,
    team: str,
    event_type: str,
    payload: dict[str, Any],
) -> list[asyncio.Task[int | None]]:
    """Queue asynchronous webhook deliveries for enabled endpoints matching team & event."""
    if not team or team == "demo-sandbox":
        return []

    stmt = select(WebhookEndpoint).where(
        WebhookEndpoint.enabled.is_(True),
        (WebhookEndpoint.team.is_(None) | (WebhookEndpoint.team == team)),
    )
    result = await db.execute(stmt)
    endpoints = result.scalars().all()

    tasks: list[asyncio.Task[int | None]] = []
    for endpoint in endpoints:
        event_types = endpoint.event_types or []
        if event_type not in event_types:
            continue

        task = asyncio.create_task(
            deliver_single_webhook(
                webhook_id=endpoint.webhook_id,
                url=endpoint.url,
                secret=endpoint.signing_secret,
                event_type=event_type,
                payload=dict(payload),
            )
        )
        _background_tasks.add(task)
        task.add_done_callback(_background_tasks.discard)
        tasks.append(task)

    return tasks


__all__ = [
    "_sign_payload",
    "deliver_single_webhook",
    "enqueue_team_webhooks",
]

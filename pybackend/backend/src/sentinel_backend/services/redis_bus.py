import asyncio
import json
import logging
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any

import redis.asyncio as aioredis

from sentinel_backend.config import settings

logger = logging.getLogger(__name__)

_redis_pool: aioredis.ConnectionPool | None = None
_pool_loop: asyncio.AbstractEventLoop | None = None


def get_redis_pool() -> aioredis.ConnectionPool:
    global _redis_pool, _pool_loop
    try:
        current_loop = asyncio.get_running_loop()
    except RuntimeError:
        current_loop = None

    if _redis_pool is None or (
        current_loop is not None and _pool_loop != current_loop
    ):
        _pool_loop = current_loop
        _redis_pool = aioredis.ConnectionPool.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            max_connections=50,
        )
    return _redis_pool


def get_redis_client() -> aioredis.Redis:
    pool = get_redis_pool()
    return aioredis.Redis(connection_pool=pool)


async def close_redis() -> None:
    global _redis_pool, _pool_loop
    if _redis_pool is not None:
        await _redis_pool.disconnect()
        _redis_pool = None
        _pool_loop = None


async def publish_event(
    channel: str, event_type: str, payload: dict[str, Any]
) -> int:
    """Serializes event to JSON and publishes to a Redis channel with timeout."""
    client = get_redis_client()
    now_utc_iso = datetime.now(UTC).isoformat()
    message = {
        "type": event_type,
        "timestamp": now_utc_iso,
        "data": payload,
    }
    raw = json.dumps(message, default=str)
    try:
        return await asyncio.wait_for(client.publish(channel, raw), timeout=3.0)
    except Exception as e:  # noqa: BLE001
        logger.warning(
            "Failed to publish event to Redis channel %s: %s", channel, e
        )
        return 0


async def subscribe_channel(
    channel: str,
) -> AsyncGenerator[dict[str, Any], None]:
    """Async generator yielding decoded JSON messages from a dedicated Redis connection,

    cleaning up pubsub subscriptions upon exit/cancellation without exhausting command pool.
    """
    client = aioredis.Redis.from_url(
        settings.REDIS_URL,
        decode_responses=True,
    )
    pubsub = client.pubsub()
    try:
        await pubsub.subscribe(channel)
        while True:
            try:
                message = await pubsub.get_message(
                    ignore_subscribe_messages=True, timeout=0.5
                )
                if message is not None:
                    data = message.get("data")
                    if isinstance(data, str):
                        try:
                            yield json.loads(data)
                        except json.JSONDecodeError:
                            yield {"raw": data}
                    elif isinstance(data, dict):
                        yield data
                else:
                    await asyncio.sleep(0.05)
            except asyncio.CancelledError:
                break
    finally:
        try:
            await pubsub.unsubscribe(channel)
        except Exception as e:  # noqa: BLE001
            logger.debug(
                "Error unsubscribing from channel %s: %s", channel, e
            )
        try:
            await pubsub.aclose()
        except Exception as e:  # noqa: BLE001
            logger.debug("Error closing pubsub for channel %s: %s", channel, e)
        try:
            await client.aclose()
        except Exception as e:  # noqa: BLE001
            logger.debug("Error closing Redis client: %s", e)


__all__ = [
    "close_redis",
    "get_redis_client",
    "get_redis_pool",
    "publish_event",
    "subscribe_channel",
]

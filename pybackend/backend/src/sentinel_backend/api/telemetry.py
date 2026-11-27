import logging
import time
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from redis.exceptions import RedisError
from sqlalchemy.ext.asyncio import AsyncSession

from sentinel_backend.api.deps import IngestContext, verify_ingest_auth
from sentinel_backend.config import settings
from sentinel_backend.db.session import get_db
from sentinel_backend.schemas.telemetry import TelemetryBatchRequest
from sentinel_backend.services.ingestion import ingest_telemetry_batch
from sentinel_backend.services.otlp_mapper import parse_otlp_request
from sentinel_backend.services.redis_bus import get_redis_client

logger = logging.getLogger(__name__)

router = APIRouter(tags=["telemetry"])

_INGEST_RATE_LIMIT_LUA = """
local key = KEYS[1]
local now_ms = tonumber(ARGV[1])
local window_ms = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
local count = tonumber(ARGV[4])
local member_prefix = ARGV[5]

redis.call("ZREMRANGEBYSCORE", key, "-inf", now_ms - window_ms)
local current = redis.call("ZCARD", key)
if (current + count) > limit then
    return {0, current}
end

local args = {}
for i = 1, count do
    table.insert(args, now_ms)
    table.insert(args, member_prefix .. ":" .. i)
end
if #args > 0 then
    for idx = 1, #args, 1000 do
        local finish = math.min(idx + 999, #args)
        redis.call("ZADD", key, unpack(args, idx, finish))
    end
end
redis.call("PEXPIRE", key, 65000)
return {1, current + count}
"""


async def _enforce_ingest_rate_limit(
    redis_client: Any,
    team: str,
    event_count: int,
) -> None:
    """Enforce atomic 60-second sliding-window ingestion limit per team."""
    if not team or team == "demo-sandbox" or event_count <= 0:
        return

    limit = settings.INGEST_RATE_LIMIT_PER_MIN
    key = f"ratelimit:ingest:{team}"
    now_ms = int(time.time() * 1000)
    member_prefix = f"{now_ms}:{uuid4().hex[:8]}"

    try:
        res = await redis_client.eval(
            _INGEST_RATE_LIMIT_LUA,
            1,
            key,
            now_ms,
            60000,
            limit,
            event_count,
            member_prefix,
        )
    except (RedisError, OSError, TimeoutError) as exc:
        logger.warning(
            "Redis rate limit check unavailable for team '%s': %s", team, exc
        )
        return

    allowed = res[0] if isinstance(res, (list, tuple)) and res else res
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"Team '{team}' ingestion rate limit exceeded "
                f"({limit} events/min)"
            ),
            headers={
                "Retry-After": "60",
                "X-RateLimit-Limit": str(limit),
            },
        )


@router.post(
    "/api/telemetry/events",
    status_code=status.HTTP_202_ACCEPTED,
)
async def post_telemetry_events(
    batch: TelemetryBatchRequest,
    ingest_ctx: IngestContext = Depends(verify_ingest_auth),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> dict[str, Any]:
    """Ingest a batch of telemetry events idempotently."""
    await _enforce_ingest_rate_limit(
        get_redis_client(),
        ingest_ctx.team,
        len(batch.events),
    )
    result = await ingest_telemetry_batch(
        db,
        batch.events,
        enforced_team=ingest_ctx.team,
    )
    return {
        "status": "accepted",
        "count": result.get("accepted", len(batch.events)),
        "run_ids": result.get("run_ids", []),
    }


@router.post(
    "/v1/traces",
    status_code=status.HTTP_200_OK,
)
@router.post(
    "/api/telemetry/v1/traces",
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
async def post_otlp_traces(
    request: Request,
    content_type: str = Header(default="application/json", alias="Content-Type"),
    ingest_ctx: IngestContext = Depends(verify_ingest_auth),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> dict[str, Any]:
    """Ingest OpenTelemetry OTLP/HTTP traces supporting application/x-protobuf and application/json."""
    raw_body = await request.body()
    try:
        events = parse_otlp_request(raw_body, content_type)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    if events:
        await _enforce_ingest_rate_limit(
            get_redis_client(),
            ingest_ctx.team,
            len(events),
        )
        await ingest_telemetry_batch(
            db,
            events,
            enforced_team=ingest_ctx.team,
        )

    return {}


__all__ = ["_enforce_ingest_rate_limit", "router"]

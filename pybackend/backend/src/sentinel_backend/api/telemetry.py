from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from sentinel_backend.api.deps import IngestContext, verify_ingest_auth
from sentinel_backend.db.session import get_db
from sentinel_backend.schemas.telemetry import TelemetryBatchRequest
from sentinel_backend.services.ingestion import ingest_telemetry_batch
from sentinel_backend.services.otlp_mapper import parse_otlp_request

router = APIRouter(tags=["telemetry"])


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
        await ingest_telemetry_batch(
            db,
            events,
            enforced_team=ingest_ctx.team,
        )

    return {}


__all__ = ["router"]

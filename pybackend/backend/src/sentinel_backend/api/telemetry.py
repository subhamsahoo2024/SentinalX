from typing import Any

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from sentinel_backend.api.deps import verify_api_key
from sentinel_backend.db.session import get_db
from sentinel_backend.schemas.telemetry import TelemetryBatchRequest
from sentinel_backend.services.ingestion import ingest_telemetry_batch

router = APIRouter(prefix="/api/telemetry", tags=["telemetry"])


@router.post(
    "/events",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(verify_api_key)],
)
async def post_telemetry_events(
    batch: TelemetryBatchRequest,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Ingest a batch of telemetry events idempotently."""
    result = await ingest_telemetry_batch(db, batch.events)
    return {
        "status": "accepted",
        "count": result.get("accepted", len(batch.events)),
        "run_ids": result.get("run_ids", []),
    }


__all__ = ["router"]


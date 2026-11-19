from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sentinel_backend.db.session import get_db
from sentinel_backend.models.alert import Alert
from sentinel_backend.schemas.alerts import AlertDTO

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


@router.get("", response_model=list[AlertDTO])
async def list_alerts(
    run_id: Annotated[
        str | None, Query(description="Filter alerts by run_id")
    ] = None,
    acknowledged: Annotated[
        bool | None,
        Query(description="Filter alerts by acknowledgement status"),
    ] = None,
    limit: Annotated[
        int, Query(ge=1, le=1000, description="Max alerts to return")
    ] = 100,
    db: Annotated[AsyncSession, Depends(get_db)] = None,  # type: ignore[assignment]
) -> list[AlertDTO]:
    """Retrieve alerts ordered by created_at DESC with optional filtering."""
    stmt = select(Alert).order_by(Alert.created_at.desc())
    if run_id is not None:
        stmt = stmt.where(Alert.run_id == run_id)
    if acknowledged is not None:
        stmt = stmt.where(Alert.acknowledged == acknowledged)
    stmt = stmt.limit(limit)

    result = await db.execute(stmt)
    alerts = result.scalars().all()
    return [AlertDTO.model_validate(a) for a in alerts]


@router.patch("/{alert_id}/ack", response_model=AlertDTO)
async def acknowledge_alert(
    alert_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AlertDTO:
    """Mark an alert as acknowledged and return the updated alert."""
    alert = await db.get(Alert, alert_id)
    if not alert:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Alert '{alert_id}' not found",
        )

    alert.acknowledged = True
    await db.commit()
    await db.refresh(alert)
    return AlertDTO.model_validate(alert)


__all__ = ["router"]


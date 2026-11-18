from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from sentinel_backend.db.session import get_db
from sentinel_backend.models.agent import Agent
from sentinel_backend.models.alert import Alert
from sentinel_backend.models.run import Run
from sentinel_backend.models.span import Span
from sentinel_backend.schemas.telemetry import (
    LineageGraphDTO,
    RunSummaryDTO,
    SpanDTO,
    SpanStatus,
)
from sentinel_backend.services.lineage_builder import (
    build_run_lineage,
    get_run_events,
)

router = APIRouter(prefix="/api/runs", tags=["runs"])


class RunListItemResponse(BaseModel):
    run_id: str
    trace_id: str
    root_agent_id: str | None
    team: str
    status: str
    started_at: datetime
    ended_at: datetime | None
    last_event_at: datetime
    total_tokens: int
    total_cost_usd: float | None
    cost_status: str
    span_count: int
    alert_count: int


@router.get("", response_model=list[RunListItemResponse])
async def list_runs(
    status: Annotated[str | None, Query()] = None,
    team: Annotated[str | None, Query()] = None,
    agent_id: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    db: Annotated[AsyncSession, Depends(get_db)] = None,  # type: ignore[assignment]
) -> list[RunListItemResponse]:
    """List runs ordered by started_at descending, supporting filtering by

    status, team, and agent_id, and annotated with span_count and alert_count.
    """
    span_sub = (
        select(Span.run_id, func.count(Span.span_id).label("span_count"))
        .group_by(Span.run_id)
        .subquery()
    )
    alert_sub = (
        select(Alert.run_id, func.count(Alert.alert_id).label("alert_count"))
        .group_by(Alert.run_id)
        .subquery()
    )

    query = (
        select(
            Run,
            func.coalesce(span_sub.c.span_count, 0).label("span_count"),
            func.coalesce(alert_sub.c.alert_count, 0).label("alert_count"),
        )
        .outerjoin(span_sub, Run.run_id == span_sub.c.run_id)
        .outerjoin(alert_sub, Run.run_id == alert_sub.c.run_id)
        .order_by(Run.started_at.desc())
        .limit(limit)
        .offset(offset)
    )

    if status:
        query = query.where(Run.status == status)
    if team:
        query = query.where(Run.team == team)
    if agent_id:
        query = query.where(Run.root_agent_id == agent_id)

    result = await db.execute(query)
    rows = result.all()

    items: list[RunListItemResponse] = []
    for run_obj, span_count, alert_count in rows:
        items.append(
            RunListItemResponse(
                run_id=run_obj.run_id,
                trace_id=run_obj.trace_id,
                root_agent_id=run_obj.root_agent_id,
                team=run_obj.team,
                status=run_obj.status,
                started_at=run_obj.started_at,
                ended_at=run_obj.ended_at,
                last_event_at=run_obj.last_event_at,
                total_tokens=run_obj.total_tokens,
                total_cost_usd=float(run_obj.total_cost_usd)
                if run_obj.total_cost_usd is not None
                else None,
                cost_status=run_obj.cost_status,
                span_count=int(span_count),
                alert_count=int(alert_count),
            )
        )
    return items


@router.get("/{run_id}", response_model=RunSummaryDTO)
async def get_run_details(
    run_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RunSummaryDTO:
    """Retrieve detailed RunSummaryDTO for a given run_id or return 404."""
    run_obj = await db.get(Run, run_id)
    if not run_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run '{run_id}' not found",
        )

    # Resolve agent metadata if root_agent_id exists
    agent_id = run_obj.root_agent_id or "unknown"
    agent_name = None
    framework = "custom"
    if run_obj.root_agent_id:
        agent_obj = await db.get(Agent, run_obj.root_agent_id)
        if agent_obj:
            agent_name = agent_obj.display_name
            framework = agent_obj.framework

    # Query span count and error count
    spans_query = select(
        func.count(Span.span_id).label("total_spans"),
        func.coalesce(
            func.count(Span.span_id).filter(
                (Span.error_class.isnot(None))
                | (Span.status == SpanStatus.FAILED.value)
            ),
            0,
        ).label("error_count"),
    ).where(Span.run_id == run_id)

    spans_res = await db.execute(spans_query)
    total_spans, error_count = spans_res.one()

    # Calculate duration
    duration_ms = None
    if run_obj.started_at and run_obj.ended_at:
        duration_ms = (
            run_obj.ended_at - run_obj.started_at
        ).total_seconds() * 1000.0

    # Map status safely to SpanStatus enum
    status_enum = SpanStatus.RUNNING
    try:
        status_enum = SpanStatus(run_obj.status)
    except ValueError:
        pass

    return RunSummaryDTO(
        run_id=run_obj.run_id,
        trace_id=run_obj.trace_id,
        agent_id=agent_id,
        agent_name=agent_name,
        team=run_obj.team,
        framework=framework,
        status=status_enum,
        started_at=run_obj.started_at,
        ended_at=run_obj.ended_at,
        duration_ms=duration_ms,
        total_spans=int(total_spans),
        total_tokens=int(run_obj.total_tokens),
        total_cost_usd=float(run_obj.total_cost_usd or 0.0),
        error_count=int(error_count),
    )


@router.get("/{run_id}/lineage", response_model=LineageGraphDTO)
async def get_run_lineage(
    run_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> LineageGraphDTO:
    """Build and return an acyclic DAG LineageGraphDTO for a given run_id."""
    return await build_run_lineage(db, run_id)


@router.get("/{run_id}/events", response_model=list[SpanDTO])
async def get_run_events_endpoint(
    run_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[SpanDTO]:
    """Retrieve all spans for a run ordered chronologically by started_at ASC for audit replay."""
    return await get_run_events(db, run_id)


__all__ = ["router"]

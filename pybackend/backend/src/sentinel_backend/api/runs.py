import logging
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from sentinel_backend.api.deps import (
    ActorContext,
    apply_team_scope,
    assert_team_access,
    get_current_actor,
    require_approver,
    verify_ingest_auth,
)
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
from sentinel_backend.services.audit import append_audit_event
from sentinel_backend.services.lineage_builder import (
    build_run_lineage,
    get_run_events,
)
from sentinel_backend.services.redis_bus import get_redis_client, publish_event

logger = logging.getLogger(__name__)

TERMINAL_RUN_STATUSES = {"SUCCEEDED", "FAILED", "CANCELLED"}

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


class RunControlStateResponse(BaseModel):
    run_id: str
    cancelled: bool
    blocked_reason: str | None = None


async def _build_run_summary(db: AsyncSession, run_obj: Run) -> RunSummaryDTO:
    agent_id = run_obj.root_agent_id or "unknown"
    agent_name = None
    framework = "custom"
    if run_obj.root_agent_id:
        agent_obj = await db.get(Agent, run_obj.root_agent_id)
        if agent_obj:
            agent_name = agent_obj.display_name
            framework = agent_obj.framework

    spans_query = select(
        func.count(Span.span_id).label("total_spans"),
        func.coalesce(
            func.count(Span.span_id).filter(
                (Span.error_class.isnot(None))
                | (Span.status == SpanStatus.FAILED.value)
            ),
            0,
        ).label("error_count"),
    ).where(Span.run_id == run_obj.run_id)

    spans_res = await db.execute(spans_query)
    total_spans, error_count = spans_res.one()

    duration_ms = None
    if run_obj.started_at and run_obj.ended_at:
        duration_ms = (
            run_obj.ended_at - run_obj.started_at
        ).total_seconds() * 1000.0

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


@router.get("", response_model=list[RunListItemResponse])
async def list_runs(
    status: Annotated[str | None, Query()] = None,
    team: Annotated[str | None, Query()] = None,
    agent_id: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    actor: Annotated[ActorContext, Depends(get_current_actor)] = None,  # type: ignore[assignment]
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
    query = apply_team_scope(query, Run.team, actor)

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
    actor: Annotated[ActorContext, Depends(get_current_actor)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RunSummaryDTO:
    """Retrieve detailed RunSummaryDTO for a given run_id or return 404."""
    run_obj = await db.get(Run, run_id)
    if not run_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run '{run_id}' not found",
        )
    assert_team_access(run_obj.team, actor)
    return await _build_run_summary(db, run_obj)


@router.post("/{run_id}/cancel", response_model=RunSummaryDTO)
async def cancel_run(
    run_id: str,
    actor: Annotated[ActorContext, Depends(require_approver)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RunSummaryDTO:
    """Cancel an active run with RBAC protection, audit logging, and Redis event broadcast."""
    run_obj = await db.get(Run, run_id)
    if not run_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run '{run_id}' not found",
        )
    assert_team_access(run_obj.team, actor)

    if run_obj.status in TERMINAL_RUN_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Run '{run_id}' is already in terminal state '{run_obj.status}'",
        )

    # Set Redis key for runtime cancellation
    try:
        redis_client = get_redis_client()
        await redis_client.set(f"run:{run_id}:cancelled", "1", ex=3600)
    except Exception as e:  # noqa: BLE001
        logger.warning(
            "Failed to set Redis key run:%s:cancelled: %s", run_id, e
        )

    now_utc = datetime.now(UTC)
    previous_status = run_obj.status
    run_obj.status = "CANCELLED"
    run_obj.ended_at = now_utc

    await append_audit_event(
        db=db,
        actor_id=actor.actor_id,
        actor_role=actor.actor_role,
        action="RUN_CANCELLED",
        target_type="run",
        target_id=run_id,
        payload={
            "team": run_obj.team,
            "previous_status": previous_status,
            "cancelled_at": now_utc.isoformat(),
        },
    )

    await db.commit()
    await db.refresh(run_obj)

    summary = await _build_run_summary(db, run_obj)
    summary_payload = summary.model_dump(mode="json")
    await publish_event(f"run:{run_id}:stream", "RUN_UPDATED", summary_payload)
    await publish_event("fleet:stream", "FLEET_UPDATED", summary_payload)

    return summary


@router.get(
    "/{run_id}/control-state",
    response_model=RunControlStateResponse,
    dependencies=[Depends(verify_ingest_auth)],
)
async def get_run_control_state(
    run_id: str,
) -> RunControlStateResponse:
    """Read active runtime control state (cancellation and budget circuit breaking) from Redis."""
    cancelled = False
    blocked_reason = None
    try:
        redis_client = get_redis_client()
        cancelled_val = await redis_client.get(f"run:{run_id}:cancelled")
        cancelled = bool(cancelled_val)
        blocked_reason_val = await redis_client.get(f"run:{run_id}:blocked")
        blocked_reason = (
            str(blocked_reason_val) if blocked_reason_val else None
        )
    except Exception as e:  # noqa: BLE001
        logger.warning(
            "Failed to read Redis control state for run %s: %s", run_id, e
        )

    return RunControlStateResponse(
        run_id=run_id,
        cancelled=cancelled,
        blocked_reason=blocked_reason,
    )


@router.get("/{run_id}/lineage", response_model=LineageGraphDTO)
async def get_run_lineage(
    run_id: str,
    actor: Annotated[ActorContext, Depends(get_current_actor)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> LineageGraphDTO:
    """Build and return an acyclic DAG LineageGraphDTO for a given run_id."""
    run_obj = await db.get(Run, run_id)
    if run_obj is not None:
        assert_team_access(run_obj.team, actor)
    return await build_run_lineage(db, run_id)


@router.get("/{run_id}/events", response_model=list[SpanDTO])
async def get_run_events_endpoint(
    run_id: str,
    actor: Annotated[ActorContext, Depends(get_current_actor)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[SpanDTO]:
    """Retrieve all spans for a run ordered chronologically by started_at ASC for audit replay."""
    run_obj = await db.get(Run, run_id)
    if run_obj is not None:
        assert_team_access(run_obj.team, actor)
    return await get_run_events(db, run_id)


__all__ = ["router"]

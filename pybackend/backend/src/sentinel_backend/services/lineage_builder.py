from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sentinel_backend.models.run import Run
from sentinel_backend.models.span import Span
from sentinel_backend.schemas.telemetry import (
    LineageEdgeDTO,
    LineageGraphDTO,
    LineageNodeDTO,
    SpanDTO,
)

FAILED_SPAN_STATUSES: set[str] = {
    "FAILED",
    "TIMED_OUT",
    "STALLED",
}


async def build_run_lineage(db: AsyncSession, run_id: str) -> LineageGraphDTO:
    """Build an acyclic DAG LineageGraphDTO for a run_id with strictly keyed span nodes

    and validated parent-child edges.
    """
    run_obj = await db.get(Run, run_id)
    if not run_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run '{run_id}' not found",
        )

    # Load all spans for the run ordered chronologically
    stmt = (
        select(Span)
        .where(Span.run_id == run_id)
        .order_by(Span.started_at.asc(), Span.attempt_number.asc())
    )
    res = await db.execute(stmt)
    spans = list(res.scalars().all())

    span_ids: set[str] = {span.span_id for span in spans}
    nodes: list[LineageNodeDTO] = []
    edges: list[LineageEdgeDTO] = []
    orphan_span_ids: list[str] = []

    # Build parent -> children map and direct cost map for subtree cost rollup
    children_map: dict[str, list[str]] = {span.span_id: [] for span in spans}
    direct_costs: dict[str, float] = {}
    for span in spans:
        if span.parent_span_id and span.parent_span_id in children_map:
            children_map[span.parent_span_id].append(span.span_id)
        if span.direct_cost_usd is not None:
            direct_costs[span.span_id] = float(span.direct_cost_usd)

    memo_descendants: dict[str, set[str]] = {}

    def get_descendants(node_id: str, path: set[str]) -> set[str]:
        if node_id in memo_descendants:
            return memo_descendants[node_id]
        descendants: set[str] = set()
        for child_id in children_map.get(node_id, []):
            if child_id in path:
                continue
            descendants.add(child_id)
            descendants.update(get_descendants(child_id, path | {child_id}))
        memo_descendants[node_id] = descendants
        return descendants

    rolled_up_costs: dict[str, float | None] = {}
    for span in spans:
        subtree_ids = {span.span_id} | get_descendants(span.span_id, {span.span_id})
        subtree_costs = [
            direct_costs[sid] for sid in subtree_ids if sid in direct_costs
        ]
        rolled_up_costs[span.span_id] = (
            round(sum(subtree_costs), 6) if subtree_costs else None
        )

    for span in spans:
        duration_ms = None
        if span.started_at and span.ended_at:
            duration_ms = (
                span.ended_at - span.started_at
            ).total_seconds() * 1000.0

        direct_cost = (
            float(span.direct_cost_usd)
            if span.direct_cost_usd is not None
            else None
        )

        cost_basis = span.cost_basis or "UNKNOWN"
        is_root_cause = (
            bool(span.is_root_cause)
            if span.is_root_cause is not None
            else False
        )
        attempt_number = span.attempt_number if span.attempt_number is not None else 1
        node_status = span.status
        if run_obj.status == "STALLED" and str(node_status).upper() in ("RUNNING", "QUEUED"):
            node_status = "STALLED"

        node = LineageNodeDTO(
            id=span.span_id,
            span_id=span.span_id,
            parent_span_id=span.parent_span_id,
            agent_id=span.agent_id,
            attempt_number=attempt_number,
            span_type=span.span_type,
            operation_name=span.operation_name,
            status=node_status,
            started_at=span.started_at,
            ended_at=span.ended_at or (span.started_at if node_status == "STALLED" else None),
            duration_ms=duration_ms,
            model_provider=span.model_provider,
            model_name=span.model_name,
            input_tokens=span.input_tokens,
            output_tokens=span.output_tokens,
            direct_cost_usd=direct_cost,
            rolled_up_cost_usd=rolled_up_costs.get(span.span_id),
            cost_basis=cost_basis,
            is_root_cause=is_root_cause,
            error_class=span.error_class,
            error_message=span.error_message,
            attributes=span.attributes or {},
        )
        nodes.append(node)

        # Build edges: only create edge if parent_span_id is known within this run
        if span.parent_span_id is not None:
            if span.parent_span_id in span_ids:
                is_failed = span.status in FAILED_SPAN_STATUSES
                edge = LineageEdgeDTO(
                    id=f"{span.parent_span_id}->{span.span_id}",
                    source=span.parent_span_id,
                    target=span.span_id,
                    is_failed_path=is_failed,
                )
                edges.append(edge)
            else:
                orphan_span_ids.append(span.span_id)

    return LineageGraphDTO(
        run_id=run_obj.run_id,
        trace_id=run_obj.trace_id,
        status=run_obj.status,
        nodes=nodes,
        edges=edges,
        orphan_span_ids=orphan_span_ids,
    )


async def get_run_events(db: AsyncSession, run_id: str) -> list[SpanDTO]:
    """Retrieve all spans for a run ordered chronologically by started_at ASC."""
    run_obj = await db.get(Run, run_id)
    if not run_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run '{run_id}' not found",
        )

    stmt = (
        select(Span)
        .where(Span.run_id == run_id)
        .order_by(Span.started_at.asc(), Span.attempt_number.asc())
    )
    res = await db.execute(stmt)
    spans = list(res.scalars().all())

    events: list[SpanDTO] = []
    for span in spans:
        duration_ms = None
        if span.started_at and span.ended_at:
            duration_ms = (
                span.ended_at - span.started_at
            ).total_seconds() * 1000.0

        direct_cost = (
            float(span.direct_cost_usd)
            if span.direct_cost_usd is not None
            else None
        )

        cost_basis = span.cost_basis or "UNKNOWN"
        is_root_cause = (
            bool(span.is_root_cause)
            if span.is_root_cause is not None
            else False
        )
        attempt_number = span.attempt_number if span.attempt_number is not None else 1

        event = SpanDTO(
            span_id=span.span_id,
            trace_id=span.trace_id,
            parent_span_id=span.parent_span_id,
            run_id=span.run_id,
            agent_id=span.agent_id,
            attempt_number=attempt_number,
            span_type=span.span_type,
            operation_name=span.operation_name,
            status=span.status,
            started_at=span.started_at,
            ended_at=span.ended_at,
            duration_ms=duration_ms,
            model_provider=span.model_provider,
            model_name=span.model_name,
            input_tokens=span.input_tokens,
            output_tokens=span.output_tokens,
            cached_tokens=span.cached_tokens,
            direct_cost_usd=direct_cost,
            cost_basis=cost_basis,
            is_root_cause=is_root_cause,
            error_class=span.error_class,
            error_message=span.error_message,
            attributes=span.attributes or {},
        )
        events.append(event)

    return events


__all__ = [
    "build_run_lineage",
    "get_run_events",
]

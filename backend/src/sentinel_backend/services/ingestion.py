import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import case, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from sentinel_backend.models.agent import Agent
from sentinel_backend.models.run import Run
from sentinel_backend.models.span import Span
from sentinel_backend.services.redis_bus import publish_event
from sentinel_sdk.schema import CanonicalEventV1, SpanStatus

logger = logging.getLogger(__name__)

TERMINAL_SPAN_STATUSES: set[str] = {
    SpanStatus.SUCCEEDED.value,
    SpanStatus.FAILED.value,
    SpanStatus.TIMED_OUT.value,
    SpanStatus.CANCELLED.value,
    "SUCCEEDED",
    "FAILED",
    "TIMED_OUT",
    "CANCELLED",
}


async def ingest_telemetry_batch(
    db: AsyncSession, events: list[CanonicalEventV1]
) -> dict[str, Any]:
    """Idempotently ingest a batch of CanonicalEventV1 telemetry events.

    1. Sorts events chronologically by started_at ascending.
    2. Upserts Agent records.
    3. Upserts Run records with root agent and status transitions.
    4. Upserts Span records with token/cost updates and attributes merge.
    5. Recomputes run.total_tokens from span sums to guarantee idempotency.
    6. Commits DB transaction.
    7. Publishes SPAN_UPSERT, RUN_UPDATED, and FLEET_UPDATED to Redis channels.
    8. Returns {"accepted": len(events), "run_ids": list(affected_run_ids)}.
    """
    if not events:
        return {"accepted": 0, "run_ids": []}

    # 1. Sort incoming events by started_at ascending
    sorted_events = sorted(events, key=lambda e: e.started_at)
    now_utc = datetime.now(timezone.utc)
    affected_run_ids: set[str] = set()

    for event in sorted_events:
        affected_run_ids.add(event.run_id)

        # a) Upsert Agent
        display_name = event.agent_name or event.agent_id
        agent_stmt = insert(Agent).values(
            agent_id=event.agent_id,
            display_name=display_name,
            framework=event.framework,
            team=event.team,
            environment="development",
            declared_tools=[],
            status="ACTIVE",
            last_seen_at=now_utc,
        )
        agent_stmt = agent_stmt.on_conflict_do_update(
            index_elements=[Agent.agent_id],
            set_={
                "display_name": agent_stmt.excluded.display_name,
                "framework": agent_stmt.excluded.framework,
                "team": agent_stmt.excluded.team,
                "status": "ACTIVE",
                "last_seen_at": agent_stmt.excluded.last_seen_at,
            },
        )
        await db.execute(agent_stmt)

        # b) Upsert Run
        is_root_span = event.parent_span_id is None
        status_str = (
            event.status.value
            if hasattr(event.status, "value")
            else str(event.status)
        )
        is_terminal = status_str in TERMINAL_SPAN_STATUSES
        is_awaiting = status_str == SpanStatus.AWAITING_APPROVAL.value

        initial_run_status = "RUNNING"
        if is_awaiting:
            initial_run_status = SpanStatus.AWAITING_APPROVAL.value
        elif is_root_span and is_terminal:
            initial_run_status = status_str

        run_insert_vals = {
            "run_id": event.run_id,
            "trace_id": event.trace_id,
            "team": event.team,
            "status": initial_run_status,
            "started_at": event.started_at,
            "ended_at": (event.ended_at or now_utc)
            if is_root_span and is_terminal
            else None,
            "last_event_at": now_utc,
            "root_agent_id": event.agent_id if is_root_span else None,
            "total_tokens": 0,
            "cost_status": "UNKNOWN",
        }

        run_update_vals: dict[str, Any] = {
            "team": event.team,
            "last_event_at": now_utc,
        }

        if is_root_span:
            run_update_vals["root_agent_id"] = event.agent_id
            run_update_vals["started_at"] = event.started_at
            if is_terminal:
                run_update_vals["status"] = status_str
                run_update_vals["ended_at"] = event.ended_at or now_utc

        if is_awaiting:
            run_update_vals["status"] = SpanStatus.AWAITING_APPROVAL.value

        run_stmt = insert(Run).values(**run_insert_vals)
        run_stmt = run_stmt.on_conflict_do_update(
            index_elements=[Run.run_id],
            set_=run_update_vals,
        )
        await db.execute(run_stmt)

        # c) Upsert Span
        direct_cost = (
            Decimal(str(event.cost.amount_usd))
            if event.cost and event.cost.amount_usd is not None
            else None
        )
        cost_basis = (
            event.cost.basis.value
            if event.cost and hasattr(event.cost.basis, "value")
            else (str(event.cost.basis) if event.cost else "UNKNOWN")
        )
        span_type = (
            event.span_type.value
            if hasattr(event.span_type, "value")
            else str(event.span_type)
        )

        span_insert_vals = {
            "span_id": event.span_id,
            "trace_id": event.trace_id,
            "parent_span_id": event.parent_span_id,
            "run_id": event.run_id,
            "agent_id": event.agent_id,
            "attempt_number": event.attempt_number,
            "span_type": span_type,
            "operation_name": event.operation_name,
            "status": status_str,
            "started_at": event.started_at,
            "ended_at": event.ended_at,
            "model_provider": event.model.provider if event.model else None,
            "model_name": event.model.name if event.model else None,
            "input_tokens": event.usage.input_tokens if event.usage else None,
            "output_tokens": event.usage.output_tokens if event.usage else None,
            "cached_tokens": event.usage.cached_tokens if event.usage else None,
            "direct_cost_usd": direct_cost,
            "cost_basis": cost_basis,
            "is_root_cause": False,
            "error_class": event.error.error_class if event.error else None,
            "error_message": event.error.message if event.error else None,
            "attributes": event.attributes or {},
        }

        span_stmt = insert(Span).values(**span_insert_vals)
        span_stmt = span_stmt.on_conflict_do_update(
            index_elements=[Span.span_id],
            set_={
                "status": span_stmt.excluded.status,
                "ended_at": func.coalesce(
                    span_stmt.excluded.ended_at, Span.ended_at
                ),
                "model_provider": func.coalesce(
                    span_stmt.excluded.model_provider, Span.model_provider
                ),
                "model_name": func.coalesce(
                    span_stmt.excluded.model_name, Span.model_name
                ),
                "input_tokens": func.coalesce(
                    span_stmt.excluded.input_tokens, Span.input_tokens
                ),
                "output_tokens": func.coalesce(
                    span_stmt.excluded.output_tokens, Span.output_tokens
                ),
                "cached_tokens": func.coalesce(
                    span_stmt.excluded.cached_tokens, Span.cached_tokens
                ),
                "direct_cost_usd": func.coalesce(
                    span_stmt.excluded.direct_cost_usd, Span.direct_cost_usd
                ),
                "cost_basis": case(
                    (
                        span_stmt.excluded.cost_basis != "UNKNOWN",
                        span_stmt.excluded.cost_basis,
                    ),
                    else_=Span.cost_basis,
                ),
                "error_class": func.coalesce(
                    span_stmt.excluded.error_class, Span.error_class
                ),
                "error_message": func.coalesce(
                    span_stmt.excluded.error_message, Span.error_message
                ),
                "attributes": Span.attributes.concat(
                    span_stmt.excluded.attributes
                ),
            },
        )
        await db.execute(span_stmt)

    # Recompute run.total_tokens and total_cost_usd for all affected run_ids
    for r_id in affected_run_ids:
        sum_query = select(
            func.coalesce(
                func.sum(
                    func.coalesce(Span.input_tokens, 0)
                    + func.coalesce(Span.output_tokens, 0)
                ),
                0,
            ),
            func.sum(Span.direct_cost_usd),
        ).where(Span.run_id == r_id)

        tokens_res = await db.execute(sum_query)
        total_tokens, total_cost = tokens_res.one()

        await db.execute(
            update(Run)
            .where(Run.run_id == r_id)
            .values(
                total_tokens=int(total_tokens),
                total_cost_usd=total_cost,
            )
        )

    # Commit DB transaction
    await db.commit()

    # Publish events to Redis
    for event in sorted_events:
        span_payload = {
            "span_id": event.span_id,
            "run_id": event.run_id,
            "trace_id": event.trace_id,
            "parent_span_id": event.parent_span_id,
            "agent_id": event.agent_id,
            "operation_name": event.operation_name,
            "span_type": event.span_type.value
            if hasattr(event.span_type, "value")
            else str(event.span_type),
            "status": event.status.value
            if hasattr(event.status, "value")
            else str(event.status),
            "started_at": event.started_at.isoformat()
            if event.started_at
            else None,
            "ended_at": event.ended_at.isoformat() if event.ended_at else None,
            "attributes": event.attributes,
        }
        await publish_event(
            f"run:{event.run_id}:stream", "SPAN_UPSERT", span_payload
        )

    for r_id in affected_run_ids:
        run_res = await db.execute(select(Run).where(Run.run_id == r_id))
        run_obj = run_res.scalar_one_or_none()
        if run_obj:
            run_payload = {
                "run_id": run_obj.run_id,
                "trace_id": run_obj.trace_id,
                "root_agent_id": run_obj.root_agent_id,
                "team": run_obj.team,
                "status": run_obj.status,
                "started_at": run_obj.started_at.isoformat()
                if run_obj.started_at
                else None,
                "ended_at": run_obj.ended_at.isoformat()
                if run_obj.ended_at
                else None,
                "last_event_at": run_obj.last_event_at.isoformat()
                if run_obj.last_event_at
                else None,
                "total_tokens": run_obj.total_tokens,
                "total_cost_usd": float(run_obj.total_cost_usd)
                if run_obj.total_cost_usd is not None
                else None,
                "cost_status": run_obj.cost_status,
            }
            await publish_event(
                f"run:{r_id}:stream", "RUN_UPDATED", run_payload
            )

    fleet_payload = {
        "run_ids": list(affected_run_ids),
        "agent_ids": list({e.agent_id for e in events}),
        "event_count": len(events),
    }
    await publish_event("fleet:stream", "FLEET_UPDATED", fleet_payload)

    return {"accepted": len(events), "run_ids": list(affected_run_ids)}


__all__ = ["ingest_telemetry_batch"]


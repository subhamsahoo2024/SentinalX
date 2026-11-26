import asyncio
import hashlib
import json
import logging
import uuid
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sentinel_backend.config import settings
from sentinel_backend.models.alert import Alert
from sentinel_backend.models.run import Run
from sentinel_backend.models.span import Span
from sentinel_backend.schemas.alerts import AlertDTO
from sentinel_backend.services.policy_service import resolve_effective_policy
from sentinel_backend.services.redis_bus import get_redis_client, publish_event

logger = logging.getLogger(__name__)

FAILED_SPAN_STATUSES: set[str] = {"FAILED", "TIMED_OUT"}
TERMINAL_IMPACT_STATUSES: set[str] = {"FAILED", "TIMED_OUT", "CANCELLED"}


def _ensure_utc(dt: datetime) -> datetime:
    """Ensure datetime has UTC timezone."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


def _get_descendants(
    span_id: str, children_by_parent: dict[str, list[Span]]
) -> list[Span]:
    """Collect all recursive descendants of a span."""
    descendants: list[Span] = []
    queue = list(children_by_parent.get(span_id, []))
    while queue:
        curr = queue.pop(0)
        descendants.append(curr)
        queue.extend(children_by_parent.get(curr.span_id, []))
    return descendants


async def _upsert_alert(
    db: AsyncSession,
    run_id: str,
    rule_id: str,
    origin_span_id: str | None,
    severity: str,
    title: str,
    evidence: dict[str, Any],
    impacted_span_ids: list[str],
    team: str | None = None,
) -> AlertDTO:
    """Query for an existing unacknowledged Alert with the same (run_id, rule_id).

    If found, update evidence, impacted_span_ids, and title in place;
    otherwise insert a new Alert with alert_<uuid12>. Publishes ALERT_CREATED
    to Redis channels run:{run_id}:stream and fleet:stream.
    """
    stmt = (
        select(Alert)
        .where(
            Alert.run_id == run_id,
            Alert.rule_id == rule_id,
            Alert.acknowledged.is_(False),
        )
        .order_by(Alert.created_at.desc())
        .limit(1)
    )
    result = await db.execute(stmt)
    existing = result.scalar_one_or_none()

    now_utc = datetime.now(UTC)

    if existing is not None:
        existing.evidence = dict(evidence)
        existing.impacted_span_ids = list(impacted_span_ids)
        existing.title = title
        if origin_span_id is not None:
            existing.origin_span_id = origin_span_id
        existing.severity = severity
        alert = existing
    else:
        alert_id = f"alert_{uuid.uuid4().hex[:12]}"
        alert = Alert(
            alert_id=alert_id,
            run_id=run_id,
            origin_span_id=origin_span_id,
            rule_id=rule_id,
            severity=severity,
            title=title,
            evidence=dict(evidence),
            impacted_span_ids=list(impacted_span_ids),
            acknowledged=False,
            created_at=now_utc,
        )
        db.add(alert)

    await db.commit()

    alert_dto = AlertDTO(
        alert_id=alert.alert_id,
        run_id=alert.run_id,
        origin_span_id=alert.origin_span_id,
        rule_id=alert.rule_id,
        severity=alert.severity,
        title=alert.title,
        evidence=dict(alert.evidence) if alert.evidence else {},
        impacted_span_ids=list(alert.impacted_span_ids)
        if alert.impacted_span_ids
        else [],
        acknowledged=bool(alert.acknowledged),
        created_at=alert.created_at,
    )

    payload = alert_dto.model_dump(mode="json")
    if team is not None:
        payload["team"] = team
    await publish_event(f"run:{run_id}:stream", "ALERT_CREATED", payload)
    await publish_event("fleet:stream", "ALERT_CREATED", payload)

    return alert_dto


async def evaluate_run_anomalies(
    db: AsyncSession, run_id: str
) -> list[AlertDTO]:
    """Evaluate deterministic causal anomalies for a given run_id.

    - Rule 1: Repeated Tool Loop (LOOP_DETECTED)
    - Rule 2: Token Budget Overrun (BUDGET_EXCEEDED)
    - Rule 3: Cascading Failure & Root-Cause Attribution (CASCADE_FAILURE)
    """
    run = await db.get(Run, run_id, populate_existing=True)
    if not run:
        logger.warning(
            "Cannot evaluate anomalies: run '%s' not found", run_id
        )
        return []

    policy = await resolve_effective_policy(
        db, team=run.team, agent_id=run.root_agent_id
    )

    stmt = (
        select(Span)
        .where(Span.run_id == run_id)
        .order_by(Span.started_at.asc(), Span.span_id.asc())
    )
    result = await db.execute(stmt)
    spans = list(result.scalars().all())

    span_by_id: dict[str, Span] = {s.span_id: s for s in spans}
    children_by_parent: dict[str, list[Span]] = defaultdict(list)
    for s in spans:
        if s.parent_span_id:
            children_by_parent[s.parent_span_id].append(s)

    triggered_alerts: list[AlertDTO] = []

    # -------------------------------------------------------------------------
    # Rule 1 — Repeated Tool Loop (LOOP_DETECTED)
    # -------------------------------------------------------------------------
    if spans:
        ref_time = max(
            filter(
                None,
                [
                    _ensure_utc(run.last_event_at)
                    if run.last_event_at
                    else None
                ]
                + [_ensure_utc(s.started_at) for s in spans],
            ),
            default=datetime.now(UTC),
        )
        window_cutoff = ref_time - timedelta(
            seconds=policy.loop_window_sec
        )

        tool_spans = [
            s
            for s in spans
            if str(s.span_type).upper() == "TOOL"
            and _ensure_utc(s.started_at) >= window_cutoff
        ]

        tool_spans_by_sig: dict[str, list[Span]] = defaultdict(list)
        for s in tool_spans:
            attrs = s.attributes if isinstance(s.attributes, dict) else {}
            inputs = attrs.get("inputs", {})
            if inputs is None:
                inputs = {}
            sort_keys = isinstance(inputs, dict)
            inputs_json = json.dumps(inputs, sort_keys=sort_keys, default=str)
            sig = hashlib.sha256(
                f"{s.agent_id}:{s.operation_name}:{inputs_json}".encode()
            ).hexdigest()[:16]
            tool_spans_by_sig[sig].append(s)

        looping_groups = [
            matching
            for matching in tool_spans_by_sig.values()
            if len(matching) >= policy.loop_threshold
        ]
        # Sort by group size descending to prioritize largest loop
        looping_groups.sort(key=len, reverse=True)

        if looping_groups:
            matching_spans = looping_groups[0]
            first_span = matching_spans[0]
            tool_name = first_span.operation_name
            repeat_count = len(matching_spans)
            impacted_ids = [m.span_id for m in matching_spans]
            evidence = {
                "tool_name": tool_name,
                "repeat_count": repeat_count,
                "threshold": policy.loop_threshold,
                "window_seconds": policy.loop_window_sec,
            }
            title = (
                f"Repeated tool loop detected: '{tool_name}' executed "
                f"{repeat_count} times in trailing {policy.loop_window_sec}s"
            )
            loop_alert = await _upsert_alert(
                db=db,
                run_id=run_id,
                rule_id="LOOP_DETECTED",
                origin_span_id=first_span.span_id,
                severity="HIGH",
                title=title,
                evidence=evidence,
                impacted_span_ids=impacted_ids,
                team=run.team,
            )
            triggered_alerts.append(loop_alert)

    # -------------------------------------------------------------------------
    # Rule 2 — Token and Cost Budget Overrun (BUDGET_EXCEEDED)
    # -------------------------------------------------------------------------
    token_exceeded = (
        run.total_tokens is not None and run.total_tokens > policy.max_tokens
    )
    cost_exceeded = (
        run.total_cost_usd is not None
        and float(run.total_cost_usd) > float(policy.max_cost_usd)
    )

    if token_exceeded or cost_exceeded:
        origin_span_id: str | None = None
        if spans:
            if cost_exceeded:
                highest_span = max(
                    spans,
                    key=lambda s: float(s.direct_cost_usd or 0.0),
                )
            else:
                highest_span = max(
                    spans,
                    key=lambda s: (s.input_tokens or 0)
                    + (s.output_tokens or 0)
                    + (s.cached_tokens or 0),
                )
            origin_span_id = highest_span.span_id

        impacted_span_ids = [
            s.span_id
            for s in spans
            if (
                ((s.input_tokens or 0) + (s.output_tokens or 0) + (s.cached_tokens or 0) > 0)
                or (s.direct_cost_usd is not None and float(s.direct_cost_usd) > 0.0)
            )
        ]
        if not impacted_span_ids and origin_span_id:
            impacted_span_ids = [origin_span_id]

        evidence = {
            "total_tokens": run.total_tokens,
            "budget_limit": policy.max_tokens,
            "max_tokens": policy.max_tokens,
            "total_cost_usd": float(run.total_cost_usd) if run.total_cost_usd is not None else None,
            "max_cost_usd": float(policy.max_cost_usd),
            "token_exceeded": token_exceeded,
            "cost_exceeded": cost_exceeded,
            "auto_block_on_budget": policy.auto_block_on_budget,
        }
        if token_exceeded and not cost_exceeded:
            title = (
                f"Run token budget exceeded: {run.total_tokens} tokens "
                f"(budget limit: {policy.max_tokens})"
            )
        elif cost_exceeded and not token_exceeded:
            title = (
                f"Run cost budget exceeded: ${float(run.total_cost_usd):.4f} USD "
                f"(budget limit: ${float(policy.max_cost_usd):.4f})"
            )
        else:
            title = (
                f"Run budget exceeded: {run.total_tokens} tokens (limit: {policy.max_tokens}), "
                f"${float(run.total_cost_usd):.4f} USD (limit: ${float(policy.max_cost_usd):.4f})"
            )

        budget_alert = await _upsert_alert(
            db=db,
            run_id=run_id,
            rule_id="BUDGET_EXCEEDED",
            origin_span_id=origin_span_id,
            severity="HIGH",
            title=title,
            evidence=evidence,
            impacted_span_ids=impacted_span_ids,
            team=run.team,
        )
        triggered_alerts.append(budget_alert)

        if policy.auto_block_on_budget:
            try:
                redis_client = get_redis_client()
                await redis_client.set(
                    f"run:{run_id}:blocked", "BUDGET_EXCEEDED", ex=3600
                )
            except Exception as e:  # noqa: BLE001
                logger.warning(
                    "Failed to set Redis key run:%s:blocked: %s", run_id, e
                )

    # -------------------------------------------------------------------------
    # Rule 3 — Cascading Failure & Root-Cause Attribution (CASCADE_FAILURE)
    # -------------------------------------------------------------------------
    failed_spans = [
        s for s in spans if str(s.status).upper() in FAILED_SPAN_STATUSES
    ]
    if failed_spans:
        # Clear root cause flags on all spans in run first
        for s in spans:
            s.is_root_cause = False

        origin_map: dict[str, Span] = {}
        for s in failed_spans:
            curr = s
            highest = s
            # Walk up parent_span_id to find highest ancestor with failed status
            while curr.parent_span_id and curr.parent_span_id in span_by_id:
                parent = span_by_id[curr.parent_span_id]
                if str(parent.status).upper() in FAILED_SPAN_STATUSES:
                    highest = parent
                    curr = parent
                else:
                    break

            # Check if highest ancestor has failed leaf tool descendants that caused the cascade
            failed_tool_descendants = [
                d
                for d in _get_descendants(highest.span_id, children_by_parent)
                if str(d.status).upper() in FAILED_SPAN_STATUSES
                and str(d.span_type).upper() == "TOOL"
            ]
            if failed_tool_descendants:
                origin_candidate = min(
                    failed_tool_descendants,
                    key=lambda x: _ensure_utc(x.started_at),
                )
            else:
                origin_candidate = highest

            # Check if child failed due to upstream sibling tool failure under same parent
            if s.parent_span_id and s.parent_span_id in span_by_id:
                siblings = [
                    sib
                    for sib in children_by_parent.get(s.parent_span_id, [])
                    if sib.span_id != s.span_id
                ]
                failed_tool_siblings = [
                    sib
                    for sib in siblings
                    if str(sib.status).upper() in FAILED_SPAN_STATUSES
                    and str(sib.span_type).upper() == "TOOL"
                ]
                if failed_tool_siblings:
                    earliest_sib = min(
                        failed_tool_siblings,
                        key=lambda x: _ensure_utc(x.started_at),
                    )
                    if _ensure_utc(earliest_sib.started_at) < _ensure_utc(
                        origin_candidate.started_at
                    ):
                        origin_candidate = earliest_sib

            origin_map[origin_candidate.span_id] = origin_candidate

        # If an origin candidate is an ancestor of another origin candidate, prefer the leaf origin
        origin_ids = set(origin_map.keys())
        for o_id in list(origin_map.keys()):
            descendants = _get_descendants(o_id, children_by_parent)
            if any(d.span_id in origin_ids for d in descendants):
                origin_map.pop(o_id, None)

        # Mark is_root_cause = True on origin spans in DB
        for origin_span in origin_map.values():
            origin_span.is_root_cause = True

        for origin_span in origin_map.values():
            descendants = _get_descendants(
                origin_span.span_id, children_by_parent
            )
            impacted_set: set[str] = {origin_span.span_id}
            for d in descendants:
                impacted_set.add(d.span_id)

            # Include failed ancestors who failed due to this root cause
            curr_ancestor = origin_span
            while (
                curr_ancestor.parent_span_id
                and curr_ancestor.parent_span_id in span_by_id
            ):
                p_span = span_by_id[curr_ancestor.parent_span_id]
                if str(p_span.status).upper() in FAILED_SPAN_STATUSES:
                    impacted_set.add(p_span.span_id)
                curr_ancestor = p_span

            origin_started = _ensure_utc(origin_span.started_at)
            for s in spans:
                if s.span_id != origin_span.span_id:
                    status_upper = str(s.status).upper()
                    if (
                        status_upper in TERMINAL_IMPACT_STATUSES
                        and _ensure_utc(s.started_at) >= origin_started
                    ):
                        impacted_set.add(s.span_id)

            impacted_span_ids = [
                s.span_id for s in spans if s.span_id in impacted_set
            ]

            if len(impacted_span_ids) >= 2:
                evidence = {
                    "origin_operation": origin_span.operation_name,
                    "origin_agent": origin_span.agent_id,
                    "error_class": origin_span.error_class,
                    "error_message": origin_span.error_message,
                    "affected_count": len(impacted_span_ids),
                }
                title = (
                    f"Cascading failure rooted at '{origin_span.operation_name}' "
                    f"affecting {len(impacted_span_ids)} spans"
                )
                cascade_alert = await _upsert_alert(
                    db=db,
                    run_id=run_id,
                    rule_id="CASCADE_FAILURE",
                    origin_span_id=origin_span.span_id,
                    severity="CRITICAL",
                    title=title,
                    evidence=evidence,
                    impacted_span_ids=impacted_span_ids,
                    team=run.team,
                )
                triggered_alerts.append(cascade_alert)

    # Persist any is_root_cause updates even if no alert was triggered
    await db.commit()

    return triggered_alerts


async def check_stalled_runs(db: AsyncSession) -> list[AlertDTO]:
    """Inspect running runs and transition stalled ones to STALLED status,

    marking all open spans as STALLED and publishing live updates.
    """
    now_utc = datetime.now(UTC)
    cutoff = now_utc - timedelta(seconds=settings.RUN_STALL_TIMEOUT_SEC)

    stmt = select(Run).where(
        Run.status == "RUNNING",
        Run.status != "AWAITING_APPROVAL",
        Run.last_event_at < cutoff,
    )
    result = await db.execute(stmt)
    stalled_runs = list(result.scalars().all())

    alerts: list[AlertDTO] = []
    for run in stalled_runs:
        run.status = "STALLED"
        run.ended_at = now_utc

        # Find all open / in-flight spans for this run and transition them to STALLED
        spans_stmt = (
            select(Span)
            .where(
                Span.run_id == run.run_id,
                Span.status.in_(["RUNNING", "QUEUED"]),
            )
            .order_by(Span.started_at.asc(), Span.span_id.asc())
        )
        spans_res = await db.execute(spans_stmt)
        open_spans = list(spans_res.scalars().all())

        for s in open_spans:
            s.status = "STALLED"
            if not s.ended_at:
                s.ended_at = now_utc
            if not s.error_class:
                s.error_class = "StallTimeoutError"
            if not s.error_message:
                s.error_message = (
                    f"Execution stalled: no telemetry received for "
                    f">{settings.RUN_STALL_TIMEOUT_SEC}s"
                )

        open_span_ids = [s.span_id for s in open_spans]
        origin_span_id = open_spans[-1].span_id if open_spans else None

        evidence = {
            "last_event_at": run.last_event_at.isoformat()
            if run.last_event_at
            else None,
            "stall_timeout_sec": settings.RUN_STALL_TIMEOUT_SEC,
            "stalled_at": now_utc.isoformat(),
            "stalled_spans_count": len(open_spans),
        }
        title = (
            f"Run '{run.run_id}' stalled: no telemetry received for "
            f">{settings.RUN_STALL_TIMEOUT_SEC}s"
        )
        alert = await _upsert_alert(
            db=db,
            run_id=run.run_id,
            rule_id="RUN_STALLED",
            origin_span_id=origin_span_id,
            severity="MEDIUM",
            title=title,
            evidence=evidence,
            impacted_span_ids=open_span_ids,
            team=run.team,
        )
        alerts.append(alert)

        # Publish SPAN_UPSERT for each stalled span so lineage graph updates live
        for s in open_spans:
            span_payload = {
                "span_id": s.span_id,
                "run_id": s.run_id,
                "trace_id": s.trace_id,
                "parent_span_id": s.parent_span_id,
                "agent_id": s.agent_id,
                "team": run.team,
                "operation_name": s.operation_name,
                "span_type": str(s.span_type),
                "status": "STALLED",
                "started_at": s.started_at.isoformat()
                if s.started_at
                else None,
                "ended_at": s.ended_at.isoformat() if s.ended_at else None,
                "attributes": s.attributes,
            }
            await publish_event(
                f"run:{run.run_id}:stream", "SPAN_UPSERT", span_payload
            )

        # Publish RUN_UPDATED and FLEET_UPDATED
        run_payload = {
            "run_id": run.run_id,
            "trace_id": run.trace_id,
            "root_agent_id": run.root_agent_id,
            "team": run.team,
            "status": run.status,
            "started_at": run.started_at.isoformat()
            if run.started_at
            else None,
            "ended_at": run.ended_at.isoformat() if run.ended_at else None,
            "last_event_at": run.last_event_at.isoformat()
            if run.last_event_at
            else None,
            "total_tokens": run.total_tokens,
            "total_cost_usd": float(run.total_cost_usd)
            if run.total_cost_usd is not None
            else None,
            "cost_status": run.cost_status,
        }
        await publish_event(
            f"run:{run.run_id}:stream", "RUN_UPDATED", run_payload
        )

        fleet_payload = {
            "team": run.team,
            "run_ids": [run.run_id],
            "agent_ids": [run.root_agent_id] if run.root_agent_id else [],
            "event_count": 0,
            "reason": "RUN_STALLED",
        }
        await publish_event("fleet:stream", "FLEET_UPDATED", fleet_payload)

    await db.commit()
    return alerts


async def stall_watchdog_loop(session_factory: Any = None) -> None:
    """Infinite async loop checking for stalled runs every 5 seconds.

    Catches asyncio.CancelledError cleanly to exit.
    """
    if session_factory is None:
        from sentinel_backend.db.session import async_session_maker

        session_factory = async_session_maker

    logger.info(
        "Starting stall watchdog loop (timeout=%ds, check_interval=5s)",
        settings.RUN_STALL_TIMEOUT_SEC,
    )
    try:
        while True:
            try:
                async with session_factory() as session:
                    await check_stalled_runs(session)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Error in stall watchdog tick")

            await asyncio.sleep(5)
    except asyncio.CancelledError:
        logger.info("Stall watchdog loop cancelled, exiting cleanly.")


__all__ = [
    "_upsert_alert",
    "check_stalled_runs",
    "evaluate_run_anomalies",
    "stall_watchdog_loop",
]

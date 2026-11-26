import math
from collections import defaultdict
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from sentinel_backend.api.deps import (
    ActorContext,
    apply_team_scope,
    get_current_actor,
)
from sentinel_backend.db.session import get_db
from sentinel_backend.models.agent import Agent
from sentinel_backend.models.alert import Alert
from sentinel_backend.models.run import Run
from sentinel_backend.models.span import Span
from sentinel_backend.schemas.telemetry import AgentSloDTO

router = APIRouter(prefix="/api/agents", tags=["agents"])

TERMINAL_RUN_STATUSES = ["SUCCEEDED", "FAILED", "TIMED_OUT", "CANCELLED"]


def _percentile(sorted_values: list[float], pct: float) -> float | None:
    """Return None if sorted_values is empty.

    Compute nearest-rank index idx = min(len(sorted_values) - 1, max(0, math.ceil((pct / 100.0) * len(sorted_values)) - 1))
    and return round(sorted_values[idx], 2).
    """
    if not sorted_values:
        return None
    idx = min(
        len(sorted_values) - 1,
        max(0, math.ceil((pct / 100.0) * len(sorted_values)) - 1),
    )
    return round(sorted_values[idx], 2)


@router.get("/slos", response_model=list[AgentSloDTO])
async def get_agent_slos(
    actor: Annotated[ActorContext, Depends(get_current_actor)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[AgentSloDTO]:
    """Calculate per-agent Service Level Objective (SLO) metrics.

    Queries team-scoped Agent rows, AGENT Span rows, and Alert rows.
    """
    agents_stmt = apply_team_scope(select(Agent), Agent.team, actor)
    agents_res = await db.execute(agents_stmt)
    agents = list(agents_res.scalars().all())

    spans_stmt = apply_team_scope(
        select(Span).join(Run, Span.run_id == Run.run_id).where(Span.span_type == "AGENT"),
        Run.team,
        actor,
    )
    spans_res = await db.execute(spans_stmt)
    agent_spans = list(spans_res.scalars().all())

    alerts_stmt = apply_team_scope(
        select(Alert).join(Run, Alert.run_id == Run.run_id),
        Run.team,
        actor,
    )
    alerts_res = await db.execute(alerts_stmt)
    alerts = list(alerts_res.scalars().all())

    # Map span_id -> agent_id for AGENT spans
    span_to_agent: dict[str, str] = {s.span_id: s.agent_id for s in agent_spans}

    # Group alerts by agent_id
    anomaly_counts: dict[str, int] = defaultdict(int)
    for alert in alerts:
        aid: str | None = None
        if alert.origin_span_id and alert.origin_span_id in span_to_agent:
            aid = span_to_agent[alert.origin_span_id]
        elif isinstance(alert.evidence, dict):
            aid = alert.evidence.get("agent_id") or alert.evidence.get("origin_agent")
        if aid:
            anomaly_counts[aid] += 1

    # Group AGENT spans by agent_id
    spans_by_agent: dict[str, list[Span]] = defaultdict(list)
    for span in agent_spans:
        spans_by_agent[span.agent_id].append(span)

    # Build agent registry (ensuring all Agent rows plus any agents present only in spans)
    agent_registry: dict[str, tuple[str, str, str]] = {}
    for agent in agents:
        agent_registry[agent.agent_id] = (
            agent.display_name or agent.agent_id,
            agent.framework or "custom",
            agent.team or "default",
        )
    for aid, s_list in spans_by_agent.items():
        if aid not in agent_registry:
            sample_span = s_list[0]
            display_name = getattr(sample_span, "operation_name", aid) or aid
            agent_registry[aid] = (display_name, "custom", "default")

    results: list[AgentSloDTO] = []
    for aid, (disp_name, framework, team) in agent_registry.items():
        spans_for_agent = spans_by_agent.get(aid, [])
        total_invocations = len(spans_for_agent)

        succeeded_count = sum(
            1 for s in spans_for_agent if str(s.status).upper() == "SUCCEEDED"
        )
        failed_count = sum(
            1
            for s in spans_for_agent
            if str(s.status).upper() in {"FAILED", "TIMED_OUT", "CANCELLED"}
        )

        success_rate_pct = (
            round((succeeded_count / total_invocations) * 100.0, 1)
            if total_invocations > 0
            else 100.0
        )

        durations_ms: list[float] = []
        total_tokens = 0
        for s in spans_for_agent:
            if s.ended_at is not None and s.started_at is not None:
                start_dt = (
                    s.started_at.replace(tzinfo=UTC)
                    if s.started_at.tzinfo is None
                    else s.started_at
                )
                end_dt = (
                    s.ended_at.replace(tzinfo=UTC)
                    if s.ended_at.tzinfo is None
                    else s.ended_at
                )
                dur = (end_dt - start_dt).total_seconds() * 1000.0
                durations_ms.append(max(0.0, dur))

            span_toks = (s.input_tokens or 0) + (s.output_tokens or 0)
            if span_toks == 0:
                # Safely inspect instance dict to avoid triggering asyncpg MissingGreenlet on unloaded relationships
                run_obj = s.__dict__.get("run")
                if run_obj is not None and getattr(run_obj, "total_tokens", None):
                    span_toks = run_obj.total_tokens or 0
                elif isinstance(s.attributes, dict):
                    span_toks = (
                        s.attributes.get("total_tokens")
                        or s.attributes.get("rolled_up_tokens")
                        or s.attributes.get("total_tokens_consumed")
                        or s.attributes.get("tokens")
                        or 0
                    )
            total_tokens += span_toks

        durations_ms.sort()
        p50_duration_ms = _percentile(durations_ms, 50.0)
        p95_duration_ms = _percentile(durations_ms, 95.0)

        avg_tokens_per_call = (
            round(total_tokens / total_invocations, 1)
            if total_invocations > 0
            else 0.0
        )

        results.append(
            AgentSloDTO(
                agent_id=aid,
                display_name=disp_name,
                framework=framework,
                team=team,
                total_invocations=total_invocations,
                succeeded_count=succeeded_count,
                failed_count=failed_count,
                success_rate_pct=success_rate_pct,
                p50_duration_ms=p50_duration_ms,
                p95_duration_ms=p95_duration_ms,
                avg_tokens_per_call=avg_tokens_per_call,
                anomaly_count=anomaly_counts.get(aid, 0),
            )
        )

    results.sort(key=lambda x: x.total_invocations, reverse=True)
    return results


class AgentResponse(BaseModel):
    agent_id: str
    display_name: str
    framework: str
    team: str
    environment: str
    declared_tools: list[Any]
    status: str
    last_seen_at: datetime
    health_status: str
    active_runs_count: int


@router.get("", response_model=list[AgentResponse])
async def list_agents(
    actor: Annotated[ActorContext, Depends(get_current_actor)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[AgentResponse]:
    """List team-scoped agents ordered by last_seen_at descending, including dynamic

    health_status ("ACTIVE" <= 60s, "IDLE" <= 15m, else "OFFLINE") and
    active_runs_count.
    """
    now = datetime.now(UTC)
    active_runs_cond = Run.status.not_in(TERMINAL_RUN_STATUSES)

    query = (
        select(
            Agent,
            func.coalesce(
                func.count(Run.run_id).filter(active_runs_cond),
                0,
            ).label("active_runs_count"),
        )
        .outerjoin(Run, Run.root_agent_id == Agent.agent_id)
        .group_by(Agent.agent_id)
        .order_by(Agent.last_seen_at.desc())
    )
    query = apply_team_scope(query, Agent.team, actor)

    result = await db.execute(query)
    rows = result.all()

    agents_list: list[AgentResponse] = []
    for agent, active_runs_count in rows:
        last_seen = agent.last_seen_at
        if last_seen.tzinfo is None:
            last_seen = last_seen.replace(tzinfo=UTC)

        diff_seconds = (now - last_seen).total_seconds()
        if diff_seconds <= 60:
            health_status = "ACTIVE"
        elif diff_seconds <= 900:  # 15 minutes
            health_status = "IDLE"
        else:
            health_status = "OFFLINE"

        agents_list.append(
            AgentResponse(
                agent_id=agent.agent_id,
                display_name=agent.display_name,
                framework=agent.framework,
                team=agent.team,
                environment=agent.environment,
                declared_tools=agent.declared_tools,
                status=agent.status,
                last_seen_at=agent.last_seen_at,
                health_status=health_status,
                active_runs_count=int(active_runs_count),
            )
        )

    return agents_list


__all__ = ["_percentile", "router"]


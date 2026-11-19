from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from sentinel_backend.db.session import get_db
from sentinel_backend.models.agent import Agent
from sentinel_backend.models.run import Run

router = APIRouter(prefix="/api/agents", tags=["agents"])

TERMINAL_RUN_STATUSES = ["SUCCEEDED", "FAILED", "TIMED_OUT", "CANCELLED"]


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
    db: AsyncSession = Depends(get_db),
) -> list[AgentResponse]:
    """List all agents ordered by last_seen_at descending, including dynamic

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


__all__ = ["router"]


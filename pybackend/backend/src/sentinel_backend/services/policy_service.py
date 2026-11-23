import logging
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from sentinel_backend.models.policy import Policy

logger = logging.getLogger(__name__)


def get_synthetic_default_policy() -> Policy:
    """Generate in-memory fallback policy when no database policies match."""
    return Policy(
        policy_id="pol_default",
        name="Global Default Governance Policy",
        team=None,
        agent_id=None,
        max_tokens=5000,
        max_cost_usd=Decimal("0.5000"),
        loop_threshold=3,
        loop_window_sec=30,
        auto_block_on_budget=False,
        protected_tools=["restart_production_cluster"],
        enabled=True,
        updated_at=datetime.now(UTC),
    )


async def seed_default_policy(db: AsyncSession) -> None:
    """If policies table is empty, insert default global governance policy."""
    count_res = await db.execute(select(func.count()).select_from(Policy))
    count = count_res.scalar_one()
    if count == 0:
        default_policy = Policy(
            policy_id="pol_default",
            name="Global Default Governance Policy",
            team=None,
            agent_id=None,
            max_tokens=5000,
            max_cost_usd=Decimal("0.5000"),
            loop_threshold=3,
            loop_window_sec=30,
            auto_block_on_budget=False,
            protected_tools=["restart_production_cluster"],
            enabled=True,
            updated_at=datetime.now(UTC),
        )
        db.add(default_policy)
        await db.commit()
        logger.info("Seeded default governance policy into database.")


async def resolve_effective_policy(
    db: AsyncSession, team: str, agent_id: str | None = None
) -> Policy:
    """Queries enabled policies and selects the most specific match in priority order:
    1) agent_id == agent_id
    2) team == team and agent_id is None
    3) team is None and agent_id is None
    (falling back to a synthetic in-memory default if none are enabled).
    """
    conditions = [
        and_(Policy.team.is_(None), Policy.agent_id.is_(None)),
        and_(Policy.team == team, Policy.agent_id.is_(None)),
    ]
    if agent_id:
        conditions.append(Policy.agent_id == agent_id)

    stmt = (
        select(Policy)
        .where(Policy.enabled.is_(True), or_(*conditions))
        .order_by(Policy.updated_at.desc())
    )
    res = await db.execute(stmt)
    raw_policies = list(res.scalars().all())
    policies = [p for p in raw_policies if isinstance(p, Policy)]

    # Priority 1: agent_id == agent_id
    if agent_id:
        for p in policies:
            if p.agent_id == agent_id and p.team == team:
                return p
        for p in policies:
            if p.agent_id == agent_id:
                return p

    # Priority 2: team == team and agent_id is None
    for p in policies:
        if p.team == team and p.agent_id is None:
            return p

    # Priority 3: team is None and agent_id is None
    for p in policies:
        if p.team is None and p.agent_id is None:
            return p

    return get_synthetic_default_policy()


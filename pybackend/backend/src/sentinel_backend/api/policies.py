import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sentinel_backend.api.deps import ActorContext, require_approver
from sentinel_backend.db.session import get_db
from sentinel_backend.models.policy import Policy
from sentinel_backend.schemas.policies import (
    PolicyCreate,
    PolicyDTO,
    PolicyUpdate,
)
from sentinel_backend.services.audit import append_audit_event

router = APIRouter(prefix="/api/policies", tags=["policies"])


@router.get("", response_model=list[PolicyDTO])
async def list_policies(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[PolicyDTO]:
    """List all governance policies ordered by enabled descending, updated_at descending."""
    stmt = select(Policy).order_by(
        Policy.enabled.desc(), Policy.updated_at.desc()
    )
    res = await db.execute(stmt)
    policies = res.scalars().all()
    return [PolicyDTO.model_validate(p) for p in policies]


@router.post("", response_model=PolicyDTO)
async def create_policy(
    body: PolicyCreate,
    actor: Annotated[ActorContext, Depends(require_approver)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PolicyDTO:
    """Create a new dynamic governance policy with RBAC protection and audit logging."""
    policy_id = body.policy_id or f"pol_{uuid.uuid4().hex[:12]}"
    now_utc = datetime.now(UTC)

    policy = Policy(
        policy_id=policy_id,
        name=body.name,
        team=body.team,
        agent_id=body.agent_id,
        max_tokens=body.max_tokens,
        max_cost_usd=Decimal(str(body.max_cost_usd)),
        loop_threshold=body.loop_threshold,
        loop_window_sec=body.loop_window_sec,
        auto_block_on_budget=body.auto_block_on_budget,
        protected_tools=body.protected_tools,
        enabled=body.enabled,
        updated_at=now_utc,
    )
    db.add(policy)

    await append_audit_event(
        db=db,
        actor_id=actor.actor_id,
        actor_role=actor.actor_role,
        action="POLICY_CREATED",
        target_type="policy",
        target_id=policy_id,
        payload=body.model_dump(mode="json"),
    )

    await db.commit()
    await db.refresh(policy)
    return PolicyDTO.model_validate(policy)


@router.patch("/{policy_id}", response_model=PolicyDTO)
async def update_policy(
    policy_id: str,
    body: PolicyUpdate,
    actor: Annotated[ActorContext, Depends(require_approver)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PolicyDTO:
    """Update an existing governance policy with RBAC protection and audit logging."""
    policy = await db.get(Policy, policy_id)
    if not policy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Policy '{policy_id}' not found",
        )

    now_utc = datetime.now(UTC)
    update_data = body.model_dump(exclude_unset=True)

    for field, value in update_data.items():
        if field == "max_cost_usd" and value is not None:
            setattr(policy, field, Decimal(str(value)))
        elif hasattr(policy, field):
            setattr(policy, field, value)

    policy.updated_at = now_utc

    await append_audit_event(
        db=db,
        actor_id=actor.actor_id,
        actor_role=actor.actor_role,
        action="POLICY_UPDATED",
        target_type="policy",
        target_id=policy_id,
        payload=update_data,
    )

    await db.commit()
    await db.refresh(policy)
    return PolicyDTO.model_validate(policy)


__all__ = ["router"]

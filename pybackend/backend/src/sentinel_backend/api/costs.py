from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sentinel_backend.api.deps import (
    ActorContext,
    get_current_actor,
    require_approver,
)
from sentinel_backend.db.session import get_db
from sentinel_backend.models.pricing import PricingVersion
from sentinel_backend.schemas.costs import (
    CostSummaryDTO,
    PricingVersionCreate,
    PricingVersionDTO,
)
from sentinel_backend.services.audit import append_audit_event
from sentinel_backend.services.cost_calculator import get_cost_summary

router = APIRouter(prefix="/api/costs", tags=["costs"])


@router.get("/summary", response_model=CostSummaryDTO)
async def get_summary(
    actor: Annotated[ActorContext, Depends(get_current_actor)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CostSummaryDTO:
    """Aggregate team-scoped costs and unknown-usage span counts grouped by

    agent_id, team, model_name, and run_id.
    """
    return await get_cost_summary(db, actor=actor)


@router.get("/pricing", response_model=list[PricingVersionDTO])
async def list_pricing(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[PricingVersionDTO]:
    """List all pricing versions ordered by effective_from descending."""
    stmt = select(PricingVersion).order_by(PricingVersion.effective_from.desc())
    res = await db.execute(stmt)
    versions = res.scalars().all()
    return [PricingVersionDTO.model_validate(p) for p in versions]


@router.post(
    "/pricing",
    response_model=PricingVersionDTO,
    status_code=status.HTTP_201_CREATED,
)
async def create_pricing_version(
    body: PricingVersionCreate,
    actor: Annotated[ActorContext, Depends(require_approver)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PricingVersionDTO:
    """Create a new pricing version and record an append-only audit event (protected by approver/admin role)."""
    now_utc = datetime.now(UTC)
    new_version = PricingVersion(
        provider=body.provider,
        model_name=body.model_name,
        version_tag=body.version_tag,
        input_rate_per_1m=Decimal(str(body.input_rate_per_1m)),
        output_rate_per_1m=Decimal(str(body.output_rate_per_1m)),
        effective_from=now_utc,
    )
    db.add(new_version)
    await db.flush()

    await append_audit_event(
        db=db,
        actor_id=actor.actor_id,
        actor_role=actor.actor_role,
        action="PRICING_UPDATED",
        target_type="pricing",
        target_id=str(new_version.id),
        payload={
            "provider": body.provider,
            "model_name": body.model_name,
            "version_tag": body.version_tag,
            "input_rate_per_1m": body.input_rate_per_1m,
            "output_rate_per_1m": body.output_rate_per_1m,
        },
    )
    await db.commit()
    await db.refresh(new_version)

    return PricingVersionDTO.model_validate(new_version)


__all__ = ["router"]

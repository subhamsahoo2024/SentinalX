from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from sentinel_backend.api.deps import (
    ActorContext,
    apply_team_scope,
    get_current_actor,
    require_approver,
    verify_api_key,
)
from sentinel_backend.db.session import get_db
from sentinel_backend.models.approval import Approval
from sentinel_backend.models.audit import AuditEvent
from sentinel_backend.models.run import Run
from sentinel_backend.models.user import UserAccount
from sentinel_backend.schemas.governance import (
    ApprovalDecisionRequest,
    ApprovalDTO,
    ApprovalRequestCreate,
    AuditEventDTO,
)
from sentinel_backend.services.audit import verify_audit_chain
from sentinel_backend.services.governance import (
    create_approval_request,
    decide_approval,
    wait_for_approval_decision,
)

router = APIRouter(tags=["governance"])


@router.post(
    "/api/approvals/request",
    response_model=ApprovalDTO,
    dependencies=[Depends(verify_api_key)],
)
async def post_approval_request(
    body: ApprovalRequestCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ApprovalDTO:
    """Submit a synchronous human-in-the-loop approval request for a tool execution."""
    return await create_approval_request(db, body)


@router.get(
    "/api/approvals/{approval_id}/wait",
    dependencies=[Depends(verify_api_key)],
)
async def wait_approval(
    approval_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    timeout: Annotated[int, Query(ge=1)] = 20,
) -> dict[str, Any]:
    """Wait synchronously for an approval decision via Redis wakeup."""
    return await wait_for_approval_decision(db, approval_id, timeout_sec=timeout)


@router.get(
    "/api/approvals",
    response_model=list[ApprovalDTO],
)
async def list_approvals(
    actor: Annotated[ActorContext, Depends(get_current_actor)],
    db: Annotated[AsyncSession, Depends(get_db)],
    status: Annotated[str | None, Query()] = None,
) -> list[ApprovalDTO]:
    """List team-scoped approval requests ordered chronologically descending."""
    stmt = select(Approval).join(Run, Approval.run_id == Run.run_id)
    stmt = apply_team_scope(stmt, Run.team, actor)
    stmt = stmt.order_by(Approval.created_at.desc())
    if status is not None:
        stmt = stmt.where(Approval.status == status)
    result = await db.execute(stmt)
    approvals = result.scalars().all()
    return [ApprovalDTO.model_validate(a) for a in approvals]


@router.post(
    "/api/approvals/{approval_id}/decision",
    response_model=ApprovalDTO,
)
async def post_approval_decision(
    approval_id: str,
    body: ApprovalDecisionRequest,
    actor: Annotated[ActorContext, Depends(require_approver)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ApprovalDTO:
    """Decide on a pending approval (APPROVED or REJECTED) with RBAC authorization and audit logging."""
    return await decide_approval(db, approval_id, body, actor)


@router.get(
    "/api/audit-events",
    response_model=list[AuditEventDTO],
)
async def list_audit_events(
    actor: Annotated[ActorContext, Depends(get_current_actor)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[AuditEventDTO]:
    """List recent governance audit log events isolated between demo and organization scopes."""
    demo_emails = select(UserAccount.email).where(
        UserAccount.is_demo_account.is_(True)
    )
    stmt = select(AuditEvent)
    if actor.is_demo:
        stmt = stmt.where(
            or_(
                AuditEvent.actor_id.endswith("@sentinel.local"),
                AuditEvent.actor_id.in_(demo_emails),
                func.coalesce(AuditEvent.payload["team"].astext, "")
                == "demo-sandbox",
            )
        )
    else:
        stmt = stmt.where(
            ~AuditEvent.actor_id.endswith("@sentinel.local"),
            ~AuditEvent.actor_id.in_(demo_emails),
            func.coalesce(AuditEvent.payload["team"].astext, "")
            != "demo-sandbox",
        )

    stmt = stmt.order_by(AuditEvent.created_at.desc()).limit(100)
    result = await db.execute(stmt)
    events = result.scalars().all()
    return [AuditEventDTO.model_validate(e) for e in events]


@router.get(
    "/api/audit-events/verify",
)
async def verify_audit_events_chain(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """Verify cryptographic hash-chain integrity of all audit events."""
    return await verify_audit_chain(db)


__all__ = ["router"]

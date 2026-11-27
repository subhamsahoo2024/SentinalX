import asyncio
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from sentinel_backend.api.deps import ActorContext, assert_team_access
from sentinel_backend.models.approval import Approval
from sentinel_backend.models.run import Run
from sentinel_backend.models.span import Span
from sentinel_backend.schemas.governance import (
    ApprovalDecisionRequest,
    ApprovalDTO,
    ApprovalRequestCreate,
)
from sentinel_backend.services.audit import append_audit_event
from sentinel_backend.services.redis_bus import publish_event, subscribe_channel
from sentinel_backend.services.webhooks import enqueue_team_webhooks

logger = logging.getLogger(__name__)


async def create_approval_request(
    db: AsyncSession, req: ApprovalRequestCreate
) -> ApprovalDTO:
    """Create a new human-in-the-loop approval request in PENDING status.

    Transitions associated span and run status to AWAITING_APPROVAL and notifies
    Redis fleet and run stream channels.
    """
    # 1. Validate that the parent Run and target Span exist
    run = await db.get(Run, req.run_id)
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"Run '{req.run_id}' not found. An approval request requires an existing "
                "run (e.g. ingested via /api/telemetry/events)."
            ),
        )

    span = await db.get(Span, req.span_id)
    if not span:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"Span '{req.span_id}' not found. An approval request requires an existing "
                "span (e.g. ingested via /api/telemetry/events)."
            ),
        )

    if span.run_id != req.run_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Span '{req.span_id}' does not belong to run '{req.run_id}'.",
        )

    # 2. Check if an approval already exists for this span
    existing_check = await db.execute(
        select(Approval).where(Approval.span_id == req.span_id)
    )
    existing_approval = existing_check.scalar_one_or_none()
    if existing_approval:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Approval request for span '{req.span_id}' already exists "
                f"(status: '{existing_approval.status}')."
            ),
        )

    approval_id = f"apr_{uuid.uuid4().hex[:12]}"
    now_utc = datetime.now(UTC)

    approval = Approval(
        approval_id=approval_id,
        run_id=req.run_id,
        span_id=req.span_id,
        agent_id=req.agent_id,
        tool_name=req.tool_name,
        sanitized_args=req.sanitized_args,
        risk_level=req.risk_level,
        policy_reason=req.policy_reason,
        status="PENDING",
        decided_by=None,
        decided_at=None,
        comment=None,
        created_at=now_utc,
    )
    db.add(approval)

    # Update target Span and Run status to AWAITING_APPROVAL
    span.status = "AWAITING_APPROVAL"
    run.status = "AWAITING_APPROVAL"

    await db.commit()
    await db.refresh(approval)

    dto = ApprovalDTO.model_validate(approval)
    payload = dto.model_dump(mode="json")
    payload["team"] = run.team

    # Publish APPROVAL_REQUIRED event
    await publish_event("fleet:stream", "APPROVAL_REQUIRED", payload)
    await publish_event(f"run:{req.run_id}:stream", "APPROVAL_REQUIRED", payload)
    await enqueue_team_webhooks(
        db,
        run.team or "default",
        "APPROVAL_REQUIRED",
        payload,
    )

    return dto


async def wait_for_approval_decision(
    db: AsyncSession, approval_id: str, timeout_sec: int = 20
) -> dict[str, Any]:
    """Wait synchronously for an approval decision via Redis pub/sub.

    If the approval was already decided, returns immediately.
    On timeout, returns status 'PENDING'.
    """
    approval = await db.get(Approval, approval_id)
    if not approval:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Approval request '{approval_id}' not found",
        )

    if approval.status != "PENDING":
        return {
            "approval_id": approval_id,
            "status": approval.status,
            "decided_by": approval.decided_by,
            "comment": approval.comment,
        }

    async def _listen() -> dict[str, Any]:
        async for msg in subscribe_channel(f"approval:{approval_id}:decision"):
            if isinstance(msg, dict):
                data = msg.get("data")
                if isinstance(data, dict):
                    return data
                return msg
        return {"approval_id": approval_id, "status": "PENDING"}

    try:
        decision = await asyncio.wait_for(_listen(), timeout=float(timeout_sec))
        return decision
    except TimeoutError:
        refreshed = await db.get(Approval, approval_id)
        if refreshed and refreshed.status != "PENDING":
            return {
                "approval_id": approval_id,
                "status": refreshed.status,
                "decided_by": refreshed.decided_by,
                "comment": refreshed.comment,
            }
        return {"approval_id": approval_id, "status": "PENDING"}


async def decide_approval(
    db: AsyncSession,
    approval_id: str,
    body: ApprovalDecisionRequest,
    actor: ActorContext,
) -> ApprovalDTO:
    """Decide an approval request (APPROVED or REJECTED) with RBAC authorization and audit logging.

    Updates span and run status, commits an append-only audit event,
    and publishes the decision to Redis channels.
    """
    stmt = (
        select(Approval)
        .where(Approval.approval_id == approval_id)
        .with_for_update()
    )
    result = await db.execute(stmt)
    approval = result.scalar_one_or_none()

    if not approval:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Approval request '{approval_id}' not found",
        )

    run = await db.get(Run, approval.run_id)
    if isinstance(run, Run):
        assert_team_access(run.team or "default", actor)

    if approval.status != "PENDING":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Approval request '{approval_id}' has already been decided "
                f"(current status: '{approval.status}')"
            ),
        )

    now_utc = datetime.now(UTC)
    approval.status = body.decision
    approval.decided_by = actor.actor_id
    approval.decided_at = now_utc
    approval.comment = body.comment

    new_span_status = "RUNNING" if body.decision == "APPROVED" else "CANCELLED"

    span = await db.get(Span, approval.span_id)
    if span:
        span.status = new_span_status
    else:
        await db.execute(
            update(Span)
            .where(Span.span_id == approval.span_id)
            .values(status=new_span_status)
        )

    if isinstance(run, Run):
        run.status = "RUNNING"
        run_team = run.team or "default"
    else:
        await db.execute(
            update(Run)
            .where(Run.run_id == approval.run_id)
            .values(status="RUNNING")
        )
        run_team = "default"

    audit_payload: dict[str, Any] = {
        "run_id": approval.run_id,
        "span_id": approval.span_id,
        "tool_name": approval.tool_name,
        "comment": body.comment,
    }
    if isinstance(run, Run):
        audit_payload["team"] = run_team

    await append_audit_event(
        db=db,
        actor_id=actor.actor_id,
        actor_role=actor.actor_role,
        action=f"APPROVAL_{body.decision}",
        target_type="approval",
        target_id=approval_id,
        payload=audit_payload,
    )

    await db.commit()
    await db.refresh(approval)

    dto = ApprovalDTO.model_validate(approval)
    decision_payload = {
        "approval_id": approval.approval_id,
        "run_id": approval.run_id,
        "span_id": approval.span_id,
        "team": run_team,
        "status": approval.status,
        "decided_by": approval.decided_by,
        "decided_at": (
            approval.decided_at.isoformat() if approval.decided_at else None
        ),
        "comment": approval.comment,
    }

    await publish_event(
        f"approval:{approval_id}:decision",
        "APPROVAL_DECIDED",
        decision_payload,
    )
    await publish_event(
        f"run:{approval.run_id}:stream",
        "APPROVAL_DECIDED",
        decision_payload,
    )
    await publish_event(
        "fleet:stream",
        "FLEET_UPDATED",
        decision_payload,
    )

    return dto


__all__ = [
    "create_approval_request",
    "decide_approval",
    "wait_for_approval_decision",
]

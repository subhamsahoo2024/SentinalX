import hashlib
import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sentinel_backend.models.audit import AuditEvent


def _compute_entry_hash(
    prev_hash: str,
    audit_id: str,
    actor_id: str,
    actor_role: str,
    action: str,
    target_type: str,
    target_id: str,
    payload: dict[str, Any],
) -> str:
    """Computes a deterministic SHA-256 entry hash over audit event attributes."""
    serialized = json.dumps(
        {
            "prev_hash": prev_hash,
            "audit_id": audit_id,
            "actor_id": actor_id,
            "actor_role": actor_role,
            "action": action,
            "target_type": target_type,
            "target_id": target_id,
            "payload": payload,
        },
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


async def append_audit_event(
    db: AsyncSession,
    actor_id: str,
    actor_role: str,
    action: str,
    target_type: str,
    target_id: str,
    payload: dict[str, Any],
) -> AuditEvent:
    """Appends an immutable audit event linked into the cryptographic hash chain.

    Queries the most recent AuditEvent to retrieve its entry_hash as the prev_hash
    for the new event (or 'GENESIS' if no audit events exist yet).
    """
    stmt = (
        select(AuditEvent)
        .order_by(AuditEvent.created_at.desc(), AuditEvent.audit_id.desc())
        .limit(1)
    )
    result = await db.execute(stmt)
    latest = result.scalar_one_or_none()

    entry_hash_val = getattr(latest, "entry_hash", None)
    prev_hash = (
        entry_hash_val
        if isinstance(entry_hash_val, str) and entry_hash_val
        else "GENESIS"
    )
    audit_id = f"audit_{uuid.uuid4().hex[:12]}"
    now_utc = datetime.now(UTC)
    latest_created = getattr(latest, "created_at", None)
    if isinstance(latest_created, datetime) and latest_created >= now_utc:
        now_utc = latest_created + timedelta(microseconds=1)

    entry_hash = _compute_entry_hash(
        prev_hash=prev_hash,
        audit_id=audit_id,
        actor_id=actor_id,
        actor_role=actor_role,
        action=action,
        target_type=target_type,
        target_id=target_id,
        payload=payload,
    )

    audit_event = AuditEvent(
        audit_id=audit_id,
        actor_id=actor_id,
        actor_role=actor_role,
        action=action,
        target_type=target_type,
        target_id=target_id,
        payload=payload,
        prev_hash=prev_hash,
        entry_hash=entry_hash,
        created_at=now_utc,
    )
    db.add(audit_event)
    await db.flush()
    return audit_event


async def verify_audit_chain(db: AsyncSession) -> dict[str, Any]:
    """Sequentially verifies the integrity of the audit event cryptographic hash chain.

    Returns:
        dict: {"valid": bool, "total_events": int, "latest_hash": str, "broken_at_audit_id": str | None}
    """
    stmt = (
        select(AuditEvent)
        .order_by(AuditEvent.created_at.asc(), AuditEvent.audit_id.asc())
    )
    result = await db.execute(stmt)
    rows = list(result.scalars().all())

    expected_prev_hash = "GENESIS"

    for row in rows:
        if row.prev_hash != expected_prev_hash:
            return {
                "valid": False,
                "total_events": len(rows),
                "latest_hash": expected_prev_hash,
                "broken_at_audit_id": row.audit_id,
            }

        computed_hash = _compute_entry_hash(
            prev_hash=row.prev_hash,
            audit_id=row.audit_id,
            actor_id=row.actor_id,
            actor_role=row.actor_role,
            action=row.action,
            target_type=row.target_type,
            target_id=row.target_id,
            payload=row.payload or {},
        )

        if row.entry_hash != computed_hash:
            return {
                "valid": False,
                "total_events": len(rows),
                "latest_hash": expected_prev_hash,
                "broken_at_audit_id": row.audit_id,
            }

        expected_prev_hash = row.entry_hash

    return {
        "valid": True,
        "total_events": len(rows),
        "latest_hash": expected_prev_hash,
        "broken_at_audit_id": None,
    }


__all__ = ["append_audit_event", "verify_audit_chain"]

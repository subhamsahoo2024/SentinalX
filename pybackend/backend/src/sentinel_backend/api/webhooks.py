import secrets
from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sentinel_backend.api.deps import ActorContext, require_admin
from sentinel_backend.db.session import get_db
from sentinel_backend.models.team import Team
from sentinel_backend.models.webhook import WebhookEndpoint
from sentinel_backend.schemas.webhooks import (
    WebhookCreate,
    WebhookDTO,
    WebhookUpdate,
)
from sentinel_backend.services.audit import append_audit_event
from sentinel_backend.services.webhooks import deliver_single_webhook

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])


async def _require_non_demo_admin(
    actor: Annotated[ActorContext, Depends(require_admin)],
) -> ActorContext:
    """Enforce non-demo organization admin privileges for webhook management."""
    if actor.is_demo:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Demo sandbox users cannot manage webhooks",
        )
    return actor


def _validate_webhook_url(raw_url: str) -> str:
    url = raw_url.strip()
    if not url.startswith(("http://", "https://")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Webhook URL must start with http:// or https://",
        )
    return url


async def _validate_target_team(db: AsyncSession, raw_team: str | None) -> str | None:
    if raw_team is None:
        return None
    normalized = raw_team.strip()
    if not normalized:
        return None
    if normalized == "demo-sandbox":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Webhooks cannot target demo-sandbox",
        )
    team = await db.get(Team, normalized)
    if team is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Team '{normalized}' not found",
        )
    return normalized


@router.get("", response_model=list[WebhookDTO])
async def list_webhooks(
    _actor: Annotated[ActorContext, Depends(_require_non_demo_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[WebhookDTO]:
    """List all configured outbound webhook endpoints ordered newest first."""
    stmt = select(WebhookEndpoint).order_by(WebhookEndpoint.created_at.desc())
    result = await db.execute(stmt)
    endpoints = result.scalars().all()
    return [WebhookDTO.model_validate(ep) for ep in endpoints]


@router.post(
    "",
    response_model=WebhookDTO,
    status_code=status.HTTP_201_CREATED,
)
async def create_webhook(
    body: WebhookCreate,
    actor: Annotated[ActorContext, Depends(_require_non_demo_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> WebhookDTO:
    """Create a new outbound webhook endpoint and log an audit event."""
    normalized_name = body.name.strip()
    if not normalized_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Webhook name must not be empty",
        )
    normalized_url = _validate_webhook_url(body.url)
    normalized_team = await _validate_target_team(db, body.team)

    webhook_id = f"wh_{uuid4().hex[:12]}"
    endpoint = WebhookEndpoint(
        webhook_id=webhook_id,
        name=normalized_name,
        team=normalized_team,
        url=normalized_url,
        signing_secret=f"whsec_{secrets.token_hex(24)}",
        event_types=list(body.event_types),
        enabled=True,
        created_at=datetime.now(UTC),
    )
    db.add(endpoint)

    await append_audit_event(
        db=db,
        actor_id=actor.actor_id,
        actor_role=actor.actor_role,
        action="WEBHOOK_CREATED",
        target_type="webhook",
        target_id=webhook_id,
        payload={
            "name": normalized_name,
            "team": normalized_team,
            "url": normalized_url,
            "event_types": list(body.event_types),
        },
    )

    await db.commit()
    await db.refresh(endpoint)
    return WebhookDTO.model_validate(endpoint)


@router.patch("/{webhook_id}", response_model=WebhookDTO)
async def update_webhook(
    webhook_id: str,
    body: WebhookUpdate,
    actor: Annotated[ActorContext, Depends(_require_non_demo_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> WebhookDTO:
    """Update an existing webhook endpoint configuration and log an audit event."""
    endpoint = await db.get(WebhookEndpoint, webhook_id)
    if endpoint is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Webhook '{webhook_id}' not found",
        )

    changes: dict[str, Any] = {}

    if "name" in body.model_fields_set and body.name is not None:
        normalized_name = body.name.strip()
        if not normalized_name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Webhook name must not be empty",
            )
        endpoint.name = normalized_name
        changes["name"] = normalized_name

    if "team" in body.model_fields_set:
        normalized_team = await _validate_target_team(db, body.team)
        endpoint.team = normalized_team
        changes["team"] = normalized_team

    if "url" in body.model_fields_set and body.url is not None:
        normalized_url = _validate_webhook_url(body.url)
        endpoint.url = normalized_url
        changes["url"] = normalized_url

    if "event_types" in body.model_fields_set and body.event_types is not None:
        endpoint.event_types = list(body.event_types)
        changes["event_types"] = list(body.event_types)

    if "enabled" in body.model_fields_set and body.enabled is not None:
        endpoint.enabled = body.enabled
        changes["enabled"] = body.enabled

    await append_audit_event(
        db=db,
        actor_id=actor.actor_id,
        actor_role=actor.actor_role,
        action="WEBHOOK_UPDATED",
        target_type="webhook",
        target_id=webhook_id,
        payload=changes,
    )

    await db.commit()
    await db.refresh(endpoint)
    return WebhookDTO.model_validate(endpoint)


@router.delete("/{webhook_id}")
async def delete_webhook(
    webhook_id: str,
    actor: Annotated[ActorContext, Depends(_require_non_demo_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """Delete an outbound webhook endpoint and log an audit event."""
    endpoint = await db.get(WebhookEndpoint, webhook_id)
    if endpoint is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Webhook '{webhook_id}' not found",
        )

    audit_payload = {
        "name": endpoint.name,
        "team": endpoint.team,
        "url": endpoint.url,
    }
    await db.delete(endpoint)

    await append_audit_event(
        db=db,
        actor_id=actor.actor_id,
        actor_role=actor.actor_role,
        action="WEBHOOK_DELETED",
        target_type="webhook",
        target_id=webhook_id,
        payload=audit_payload,
    )

    await db.commit()
    return {"status": "deleted", "webhook_id": webhook_id}


@router.post("/{webhook_id}/test")
async def test_webhook(
    webhook_id: str,
    _actor: Annotated[ActorContext, Depends(_require_non_demo_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """Immediately send a TEST_PING event to verify webhook connectivity."""
    endpoint = await db.get(WebhookEndpoint, webhook_id)
    if endpoint is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Webhook '{webhook_id}' not found",
        )

    status_code = await deliver_single_webhook(
        webhook_id=endpoint.webhook_id,
        url=endpoint.url,
        secret=endpoint.signing_secret,
        event_type="TEST_PING",
        payload={
            "message": "SENTINEL-X webhook connectivity verified",
            "team": endpoint.team or "all-teams",
        },
    )
    return {
        "delivered": status_code is not None and 200 <= status_code < 300,
        "status_code": status_code,
    }


__all__ = ["router"]

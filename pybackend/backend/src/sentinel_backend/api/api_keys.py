import hashlib
import secrets
from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sentinel_backend.api.deps import ActorContext, require_admin
from sentinel_backend.db.session import get_db
from sentinel_backend.models.api_key import ApiKey
from sentinel_backend.models.team import Team
from sentinel_backend.schemas.api_keys import (
    ApiKeyCreate,
    ApiKeyCreatedDTO,
    ApiKeyDTO,
)
from sentinel_backend.services.audit import append_audit_event

router = APIRouter(prefix="/api/api-keys", tags=["api-keys"])


async def _require_non_demo_admin(
    actor: Annotated[ActorContext, Depends(require_admin)],
) -> ActorContext:
    """Enforce non-demo organization admin privileges for API key management."""
    if actor.is_demo:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Demo sandbox users cannot manage API keys",
        )
    return actor


@router.get("", response_model=list[ApiKeyDTO])
async def list_api_keys(
    _actor: Annotated[ActorContext, Depends(_require_non_demo_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[ApiKeyDTO]:
    """List all minted team API keys ordered by creation timestamp descending."""
    stmt = select(ApiKey).order_by(ApiKey.created_at.desc())
    result = await db.execute(stmt)
    keys = result.scalars().all()
    return [ApiKeyDTO.model_validate(key) for key in keys]


@router.post(
    "",
    response_model=ApiKeyCreatedDTO,
    status_code=status.HTTP_201_CREATED,
)
async def create_api_key(
    body: ApiKeyCreate,
    actor: Annotated[ActorContext, Depends(_require_non_demo_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ApiKeyCreatedDTO:
    """Mint a new team-bound ingestion API key and return the raw secret once."""
    normalized_name = body.name.strip()
    if not normalized_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="API key name must not be empty",
        )

    normalized_team = body.team.strip()
    if not normalized_team or normalized_team == "demo-sandbox":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid target team for production API key",
        )

    team = await db.get(Team, normalized_team)
    if team is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Team '{normalized_team}' not found",
        )

    raw_key = f"sk_live_{secrets.token_hex(24)}"
    key_prefix = raw_key[:12]
    key_hash = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
    key_id = f"key_{uuid4().hex[:12]}"

    api_key = ApiKey(
        key_id=key_id,
        name=normalized_name,
        team=normalized_team,
        key_prefix=key_prefix,
        key_hash=key_hash,
        created_by=actor.actor_id,
        created_at=datetime.now(UTC),
    )
    db.add(api_key)

    await append_audit_event(
        db=db,
        actor_id=actor.actor_id,
        actor_role=actor.actor_role,
        action="API_KEY_CREATED",
        target_type="api_key",
        target_id=key_id,
        payload={
            "name": normalized_name,
            "team": normalized_team,
            "key_prefix": key_prefix,
        },
    )

    await db.commit()
    await db.refresh(api_key)
    dto = ApiKeyDTO.model_validate(api_key)
    return ApiKeyCreatedDTO(**dto.model_dump(), raw_key=raw_key)


@router.delete("/{key_id}")
async def revoke_api_key(
    key_id: str,
    actor: Annotated[ActorContext, Depends(_require_non_demo_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """Soft-revoke a team-bound API key while preserving audit history."""
    api_key = await db.get(ApiKey, key_id)
    if api_key is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"API key '{key_id}' not found",
        )

    api_key.revoked_at = datetime.now(UTC)

    await append_audit_event(
        db=db,
        actor_id=actor.actor_id,
        actor_role=actor.actor_role,
        action="API_KEY_REVOKED",
        target_type="api_key",
        target_id=key_id,
        payload={
            "name": api_key.name,
            "team": api_key.team,
            "key_prefix": api_key.key_prefix,
        },
    )

    await db.commit()
    return {"status": "revoked", "key_id": key_id}


__all__ = ["router"]


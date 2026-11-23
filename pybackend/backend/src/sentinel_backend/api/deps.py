import secrets
from typing import Any

from fastapi import Depends, Header, HTTPException, status
from pydantic import BaseModel

from sentinel_backend.config import settings

VALID_ACTOR_ROLES = {"viewer", "operator", "approver", "admin"}


class ActorContext(BaseModel):
    actor_id: str
    actor_role: str

    def __init__(
        self,
        actor_id: str | None = None,
        actor_role: str | None = None,
        **data: Any,
    ) -> None:
        if actor_id is not None:
            data["actor_id"] = actor_id
        if actor_role is not None:
            data["actor_role"] = actor_role
        super().__init__(**data)


async def verify_api_key(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> str:
    """Verifies that the provided API key matches the configured SENTINEL_API_KEY.

    Raises 401 Unauthorized if missing or invalid.
    """
    if not x_api_key or not secrets.compare_digest(
        x_api_key, settings.SENTINEL_API_KEY
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    return x_api_key


async def verify_ingest_auth(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> str:
    """Verifies ingest authentication via either X-API-Key or Authorization: Bearer <token>.

    Matches against configured SENTINEL_API_KEY.
    Raises 401 Unauthorized if missing or invalid.
    """
    provided_key: str | None = None

    if x_api_key:
        provided_key = x_api_key
    elif authorization:
        parts = authorization.split(maxsplit=1)
        if len(parts) == 2 and parts[0].lower() == "bearer":
            provided_key = parts[1].strip()
        else:
            provided_key = authorization.strip()

    if not provided_key or not secrets.compare_digest(
        provided_key, settings.SENTINEL_API_KEY
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return provided_key


async def get_current_actor(
    x_actor_id: str = Header(default="operator-1"),
    x_actor_role: str = Header(default="approver"),
) -> ActorContext:
    """Extracts and validates the current actor from request headers.

    Valid roles: viewer, operator, approver, admin.
    Raises 400 Bad Request if x_actor_role is invalid.
    """
    if x_actor_role not in VALID_ACTOR_ROLES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Invalid actor role '{x_actor_role}'. "
                f"Must be one of: {', '.join(sorted(VALID_ACTOR_ROLES))}"
            ),
        )
    return ActorContext(actor_id=x_actor_id, actor_role=x_actor_role)


async def require_approver(
    actor: ActorContext = Depends(get_current_actor),  # noqa: B008
) -> ActorContext:
    """Enforces approver or admin role for HITL governance actions.

    Raises 403 Forbidden if the actor does not have approver privileges.
    """
    if actor.actor_role not in {"approver", "admin"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Actor role '{actor.actor_role}' does not have approver privileges",
        )
    return actor


__all__ = [
    "VALID_ACTOR_ROLES",
    "ActorContext",
    "get_current_actor",
    "require_approver",
    "verify_api_key",
    "verify_ingest_auth",
]

import secrets
from typing import Annotated, Any

import jwt
from fastapi import Depends, Header, HTTPException, status
from pydantic import BaseModel

from sentinel_backend.config import settings

VALID_ACTOR_ROLES = {"viewer", "operator", "approver", "admin"}


class ActorContext(BaseModel):
    actor_id: str
    actor_role: str
    display_name: str | None = None

    def __init__(
        self,
        actor_id: str | None = None,
        actor_role: str | None = None,
        display_name: str | None = None,
        **data: Any,
    ) -> None:
        if actor_id is not None:
            data["actor_id"] = actor_id
        if actor_role is not None:
            data["actor_role"] = actor_role
        if display_name is not None:
            data["display_name"] = display_name
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
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
    x_actor_id: Annotated[str, Header()] = "operator-1",
    x_actor_role: Annotated[str, Header()] = "approver",
) -> ActorContext:
    """Extracts and validates the current actor from JWT Bearer token or development headers.

    If an Authorization: Bearer <token> header is provided, cryptographically decodes
    and validates the token with settings.JWT_SECRET (HS256).
    If no Bearer token is provided and settings.ALLOW_DEV_HEADERS is True, falls back to
    x_actor_id and x_actor_role.
    Otherwise raises 401 Unauthorized.
    """
    raw_auth = authorization if isinstance(authorization, str) else None
    if raw_auth and raw_auth.startswith("Bearer "):
        token = raw_auth[len("Bearer ") :].strip()
        try:
            claims = jwt.decode(
                token, settings.JWT_SECRET, algorithms=["HS256"]
            )
        except jwt.PyJWTError as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid or expired authentication token: {e}",
                headers={"WWW-Authenticate": "Bearer"},
            ) from e

        actor_role = claims.get("role")
        if actor_role not in VALID_ACTOR_ROLES:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid actor role '{actor_role}' in token claims",
                headers={"WWW-Authenticate": "Bearer"},
            )

        actor_id = claims.get("email") or claims.get("sub") or "unknown"
        display_name = claims.get("name") or actor_id
        return ActorContext(
            actor_id=actor_id,
            actor_role=actor_role,
            display_name=display_name,
        )

    if settings.ALLOW_DEV_HEADERS:
        actor_id_val = x_actor_id if isinstance(x_actor_id, str) else "operator-1"
        actor_role_val = x_actor_role if isinstance(x_actor_role, str) else "approver"
        if actor_role_val not in VALID_ACTOR_ROLES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Invalid actor role '{actor_role_val}'. "
                    f"Must be one of: {', '.join(sorted(VALID_ACTOR_ROLES))}"
                ),
            )
        return ActorContext(
            actor_id=actor_id_val,
            actor_role=actor_role_val,
            display_name=actor_id_val,
        )

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Missing or invalid authentication token",
        headers={"WWW-Authenticate": "Bearer"},
    )


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

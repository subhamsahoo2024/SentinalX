from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from pwdlib import PasswordHash
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sentinel_backend.api.deps import ActorContext, get_current_actor
from sentinel_backend.config import settings
from sentinel_backend.db.session import get_db
from sentinel_backend.models.user import UserAccount

router = APIRouter(prefix="/api/auth", tags=["auth"])
password_hasher = PasswordHash.recommended()


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str
    password: str


class UserProfileDTO(BaseModel):
    user_id: str
    email: str
    display_name: str
    role: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserProfileDTO


class CurrentUserResponse(BaseModel):
    actor_id: str
    actor_role: str
    display_name: str


@router.post("/login", response_model=LoginResponse)
async def login(
    body: LoginRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> LoginResponse:
    """Authenticates a user via email and password, issuing an HS256 JWT access token."""
    normalized_email = body.email.strip().lower()
    stmt = select(UserAccount).where(UserAccount.email == normalized_email)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user or not password_hasher.verify(body.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    now_utc = datetime.now(UTC)
    expires_at = now_utc + timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
    claims: dict[str, Any] = {
        "sub": user.user_id,
        "email": user.email,
        "name": user.display_name,
        "role": user.role,
        "exp": expires_at,
    }

    token = jwt.encode(claims, settings.JWT_SECRET, algorithm="HS256")

    return LoginResponse(
        access_token=token,
        token_type="bearer",
        user=UserProfileDTO(
            user_id=user.user_id,
            email=user.email,
            display_name=user.display_name,
            role=user.role,
        ),
    )


@router.get("/me", response_model=CurrentUserResponse)
async def get_current_user_profile(
    actor: Annotated[ActorContext, Depends(get_current_actor)],
) -> CurrentUserResponse:
    """Returns the authenticated actor context (actor_id, actor_role, and display_name)."""
    return CurrentUserResponse(
        actor_id=actor.actor_id,
        actor_role=actor.actor_role,
        display_name=actor.display_name or actor.actor_id,
    )


__all__ = ["router"]

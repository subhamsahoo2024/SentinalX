import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from pwdlib import PasswordHash
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from sentinel_backend.api.deps import ActorContext, get_current_actor
from sentinel_backend.config import settings
from sentinel_backend.db.session import get_db
from sentinel_backend.models.user import UserAccount
from sentinel_backend.services.audit import append_audit_event

router = APIRouter(prefix="/api/auth", tags=["auth"])
password_hasher = PasswordHash.recommended()


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str
    password: str


class BootstrapAdminRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str
    password: str = Field(min_length=1)
    display_name: str = "Organization Admin"


class UserProfileDTO(BaseModel):
    user_id: str
    email: str
    display_name: str
    role: str
    allowed_teams: list[str] = Field(default_factory=lambda: ["*"])
    is_demo: bool = False


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserProfileDTO


class CurrentUserResponse(BaseModel):
    actor_id: str
    actor_role: str
    display_name: str
    allowed_teams: list[str] = Field(default_factory=lambda: ["*"])
    is_demo: bool = False


def _issue_user_jwt(
    user: UserAccount,
    expires_minutes: int | None = None,
) -> dict[str, Any]:
    """Issues an HS256 JWT and user profile payload for an authenticated account."""
    ttl_minutes = (
        expires_minutes
        if expires_minutes is not None
        else settings.JWT_EXPIRE_MINUTES
    )
    now_utc = datetime.now(UTC)
    expires_at = now_utc + timedelta(minutes=ttl_minutes)
    claims: dict[str, Any] = {
        "sub": user.user_id,
        "email": user.email,
        "name": user.display_name,
        "role": user.role,
        "allowed_teams": user.allowed_teams,
        "is_demo": user.is_demo_account,
        "exp": expires_at,
    }

    token = jwt.encode(claims, settings.JWT_SECRET, algorithm="HS256")
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "user_id": user.user_id,
            "email": user.email,
            "display_name": user.display_name,
            "role": user.role,
            "allowed_teams": user.allowed_teams,
            "is_demo": user.is_demo_account,
        },
    }


@router.post("/login", response_model=LoginResponse)
async def login(
    body: LoginRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
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

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is deactivated",
        )

    return _issue_user_jwt(user)


@router.post("/bootstrap-admin", response_model=LoginResponse)
async def bootstrap_admin(
    body: BootstrapAdminRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """Creates the first non-demo organization admin account when none exists."""
    count_stmt = (
        select(func.count())
        .select_from(UserAccount)
        .where(UserAccount.is_demo_account.is_(False))
    )
    count_result = await db.execute(count_stmt)
    non_demo_count = int(count_result.scalar_one() or 0)
    if non_demo_count > 0:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Organization admin already initialized",
        )

    normalized_email = body.email.strip().lower()
    if not normalized_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email must not be empty",
        )

    now_utc = datetime.now(UTC)
    admin_user = UserAccount(
        user_id=f"usr_{uuid.uuid4().hex[:12]}",
        email=normalized_email,
        display_name=body.display_name.strip() or "Organization Admin",
        password_hash=password_hasher.hash(body.password),
        role="admin",
        allowed_teams=["*"],
        is_active=True,
        is_demo_account=False,
        created_at=now_utc,
    )
    db.add(admin_user)

    await append_audit_event(
        db=db,
        actor_id=admin_user.email,
        actor_role=admin_user.role,
        action="ADMIN_BOOTSTRAPPED",
        target_type="user",
        target_id=admin_user.user_id,
        payload={
            "email": admin_user.email,
            "display_name": admin_user.display_name,
        },
    )

    await db.commit()
    await db.refresh(admin_user)
    return _issue_user_jwt(admin_user)


@router.post("/demo-login", response_model=LoginResponse)
async def demo_login(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """Issues a short-lived sandbox JWT for the demo approver account when enabled."""
    if not settings.ENABLE_DEMO_SANDBOX:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Demo sandbox is disabled",
        )

    stmt = select(UserAccount).where(
        UserAccount.email == "approver@sentinel.local",
        UserAccount.is_demo_account.is_(True),
    )
    result = await db.execute(stmt)
    demo_user = result.scalar_one_or_none()
    if demo_user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Demo sandbox account not found",
        )

    if not demo_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Demo sandbox account is deactivated",
        )

    return _issue_user_jwt(demo_user, expires_minutes=120)


@router.get("/me", response_model=CurrentUserResponse)
async def get_current_user_profile(
    actor: Annotated[ActorContext, Depends(get_current_actor)],
) -> CurrentUserResponse:
    """Returns the authenticated actor context including allowed teams and demo flag."""
    return CurrentUserResponse(
        actor_id=actor.actor_id,
        actor_role=actor.actor_role,
        display_name=actor.display_name or actor.actor_id,
        allowed_teams=actor.allowed_teams,
        is_demo=actor.is_demo,
    )


__all__ = ["router"]

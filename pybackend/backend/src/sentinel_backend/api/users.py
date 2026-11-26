import uuid
from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pwdlib import PasswordHash
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sentinel_backend.api.deps import (
    ActorContext,
    get_current_actor,
    require_admin,
)
from sentinel_backend.db.session import get_db
from sentinel_backend.models.team import Team
from sentinel_backend.models.user import UserAccount
from sentinel_backend.services.audit import append_audit_event

router = APIRouter(prefix="/api", tags=["users"])
password_hasher = PasswordHash.recommended()

UserRole = Literal["viewer", "operator", "approver", "admin"]


class TeamCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    team_id: str = Field(min_length=1)
    display_name: str = Field(min_length=1)
    description: str | None = None


class TeamDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    team_id: str
    display_name: str
    description: str | None = None
    created_at: datetime


class UserProvisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=1)
    display_name: str = Field(min_length=1)
    password: str = Field(min_length=1)
    role: UserRole
    allowed_teams: list[str] = Field(default_factory=lambda: ["*"])


class UserUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: UserRole | None = None
    allowed_teams: list[str] | None = None
    is_active: bool | None = None


class UserSummaryDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: str
    email: str
    display_name: str
    role: str
    allowed_teams: list[str]
    is_active: bool
    created_at: datetime


@router.get("/teams", response_model=list[TeamDTO])
async def list_teams(
    _actor: Annotated[ActorContext, Depends(get_current_actor)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[TeamDTO]:
    """List all organizational teams ordered by display_name ascending."""
    stmt = select(Team).order_by(Team.display_name.asc())
    result = await db.execute(stmt)
    teams = result.scalars().all()
    return [TeamDTO.model_validate(team) for team in teams]


@router.post(
    "/teams",
    response_model=TeamDTO,
    status_code=status.HTTP_201_CREATED,
)
async def create_team(
    body: TeamCreateRequest,
    actor: Annotated[ActorContext, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TeamDTO:
    """Create a new organizational team (admin only) and record an audit event."""
    normalized_team_id = body.team_id.strip()
    if not normalized_team_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="team_id must not be empty",
        )

    existing = await db.get(Team, normalized_team_id)
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Team '{normalized_team_id}' already exists",
        )

    team = Team(
        team_id=normalized_team_id,
        display_name=body.display_name.strip(),
        description=body.description,
        created_at=datetime.now(UTC),
    )
    db.add(team)

    await append_audit_event(
        db=db,
        actor_id=actor.actor_id,
        actor_role=actor.actor_role,
        action="TEAM_CREATED",
        target_type="team",
        target_id=team.team_id,
        payload={
            "team_id": team.team_id,
            "display_name": team.display_name,
            "description": team.description,
        },
    )

    await db.commit()
    await db.refresh(team)
    return TeamDTO.model_validate(team)


@router.get("/users", response_model=list[UserSummaryDTO])
async def list_users(
    _actor: Annotated[ActorContext, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[UserSummaryDTO]:
    """List all non-demo organizational user accounts (admin only)."""
    stmt = (
        select(UserAccount)
        .where(UserAccount.is_demo_account.is_(False))
        .order_by(UserAccount.created_at.asc(), UserAccount.email.asc())
    )
    result = await db.execute(stmt)
    users = result.scalars().all()
    return [UserSummaryDTO.model_validate(user) for user in users]


@router.post(
    "/users",
    response_model=UserSummaryDTO,
    status_code=status.HTTP_201_CREATED,
)
async def provision_user(
    body: UserProvisionRequest,
    actor: Annotated[ActorContext, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserSummaryDTO:
    """Provision a new non-demo employee account (admin only) with audit logging."""
    normalized_email = body.email.strip().lower()
    if not normalized_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email must not be empty",
        )

    existing_stmt = select(UserAccount).where(UserAccount.email == normalized_email)
    existing_res = await db.execute(existing_stmt)
    if existing_res.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"User with email '{normalized_email}' already exists",
        )

    user = UserAccount(
        user_id=f"usr_{uuid.uuid4().hex[:12]}",
        email=normalized_email,
        display_name=body.display_name.strip(),
        password_hash=password_hasher.hash(body.password),
        role=body.role,
        allowed_teams=body.allowed_teams,
        is_active=True,
        is_demo_account=False,
        created_at=datetime.now(UTC),
    )
    db.add(user)

    await append_audit_event(
        db=db,
        actor_id=actor.actor_id,
        actor_role=actor.actor_role,
        action="USER_PROVISIONED",
        target_type="user",
        target_id=user.user_id,
        payload={
            "email": user.email,
            "display_name": user.display_name,
            "role": user.role,
            "allowed_teams": user.allowed_teams,
        },
    )

    await db.commit()
    await db.refresh(user)
    return UserSummaryDTO.model_validate(user)


@router.patch("/users/{user_id}", response_model=UserSummaryDTO)
async def update_user(
    user_id: str,
    body: UserUpdateRequest,
    actor: Annotated[ActorContext, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserSummaryDTO:
    """Update role, allowed_teams, or active status for an employee account (admin only)."""
    user = await db.get(UserAccount, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User '{user_id}' not found",
        )

    if user.is_demo_account:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot modify demo sandbox accounts",
        )

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if value is not None and hasattr(user, field):
            setattr(user, field, value)

    await append_audit_event(
        db=db,
        actor_id=actor.actor_id,
        actor_role=actor.actor_role,
        action="USER_UPDATED",
        target_type="user",
        target_id=user.user_id,
        payload=update_data,
    )

    await db.commit()
    await db.refresh(user)
    return UserSummaryDTO.model_validate(user)


__all__ = ["router"]


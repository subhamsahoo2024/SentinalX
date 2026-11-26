from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from sentinel_backend.config import settings
from sentinel_backend.db.session import get_db
from sentinel_backend.models.user import UserAccount

router = APIRouter(prefix="/api/system", tags=["system"])


class SystemConfigResponse(BaseModel):
    demo_sandbox_enabled: bool
    needs_bootstrap: bool


@router.get("/config", response_model=SystemConfigResponse)
async def get_system_config(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SystemConfigResponse:
    """Returns public system bootstrap and demo sandbox availability flags."""
    stmt = (
        select(func.count())
        .select_from(UserAccount)
        .where(UserAccount.is_demo_account.is_(False))
    )
    result = await db.execute(stmt)
    non_demo_count = int(result.scalar_one() or 0)
    return SystemConfigResponse(
        demo_sandbox_enabled=settings.ENABLE_DEMO_SANDBOX,
        needs_bootstrap=non_demo_count == 0,
    )


__all__ = ["SystemConfigResponse", "router"]


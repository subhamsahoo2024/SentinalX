import logging
import uuid
from datetime import UTC, datetime

from pwdlib import PasswordHash
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from sentinel_backend.config import settings
from sentinel_backend.models.team import Team
from sentinel_backend.models.user import UserAccount

logger = logging.getLogger(__name__)

password_hash_helper = PasswordHash.recommended()

DEFAULT_TEAMS: list[dict[str, str]] = [
    {
        "team_id": "it-ops",
        "display_name": "IT Operations",
        "description": "Infrastructure, incident response, and IT operations agents",
    },
    {
        "team_id": "customer-support",
        "display_name": "Customer Support",
        "description": "Customer service and ticket triage agents",
    },
    {
        "team_id": "fraud-detection",
        "display_name": "Fraud Detection",
        "description": "Transaction risk scoring and fraud investigation agents",
    },
    {
        "team_id": "demo-sandbox",
        "display_name": "Demo Sandbox",
        "description": "Isolated sandbox team for demonstration scenarios and demo accounts",
    },
]

DEFAULT_USERS: list[dict[str, str]] = [
    {
        "user_id": "usr_admin",
        "email": "admin@sentinel.local",
        "display_name": "Priya Nair (Admin)",
        "role": "admin",
    },
    {
        "user_id": "usr_approver",
        "email": "approver@sentinel.local",
        "display_name": "Arjun Mehta (Approver)",
        "role": "approver",
    },
    {
        "user_id": "usr_operator",
        "email": "operator@sentinel.local",
        "display_name": "Devika Rao (Operator)",
        "role": "operator",
    },
    {
        "user_id": "usr_viewer",
        "email": "viewer@sentinel.local",
        "display_name": "Rohan Das (Auditor)",
        "role": "viewer",
    },
]


async def seed_default_users(db: AsyncSession) -> None:
    """Seeds baseline teams, demo sandbox users (if enabled), and initial admin (if configured)."""
    now_utc = datetime.now(UTC)
    changed = False

    team_result = await db.execute(select(Team).limit(1))
    if team_result.scalar_one_or_none() is None:
        logger.info("Seeding baseline organizational teams...")
        for team_info in DEFAULT_TEAMS:
            db.add(
                Team(
                    team_id=team_info["team_id"],
                    display_name=team_info["display_name"],
                    description=team_info["description"],
                    created_at=now_utc,
                )
            )
        changed = True

    if settings.ENABLE_DEMO_SANDBOX:
        demo_emails = [user_info["email"] for user_info in DEFAULT_USERS]
        demo_result = await db.execute(
            select(UserAccount)
            .where(
                or_(
                    UserAccount.is_demo_account.is_(True),
                    UserAccount.email.in_(demo_emails),
                )
            )
            .limit(1)
        )
        if demo_result.scalar_one_or_none() is None:
            logger.info("Seeding demo user accounts with Argon2 password hashes...")
            hashed_pwd = password_hash_helper.hash("sentinel123")
            for user_info in DEFAULT_USERS:
                db.add(
                    UserAccount(
                        user_id=user_info["user_id"],
                        email=user_info["email"],
                        display_name=user_info["display_name"],
                        password_hash=hashed_pwd,
                        role=user_info["role"],
                        allowed_teams=["demo-sandbox"],
                        is_active=True,
                        is_demo_account=True,
                        created_at=now_utc,
                    )
                )
            changed = True

    initial_email = (settings.INITIAL_ADMIN_EMAIL or "").strip().lower()
    initial_password = settings.INITIAL_ADMIN_PASSWORD or ""
    if initial_email and initial_password:
        admin_result = await db.execute(
            select(UserAccount)
            .where(
                UserAccount.role == "admin",
                UserAccount.is_demo_account.is_(False),
            )
            .limit(1)
        )
        if admin_result.scalar_one_or_none() is None:
            logger.info("Creating initial real admin account for %s...", initial_email)
            db.add(
                UserAccount(
                    user_id=f"usr_{uuid.uuid4().hex[:12]}",
                    email=initial_email,
                    display_name="Initial Admin",
                    password_hash=password_hash_helper.hash(initial_password),
                    role="admin",
                    allowed_teams=["*"],
                    is_active=True,
                    is_demo_account=False,
                    created_at=now_utc,
                )
            )
            changed = True

    if changed:
        await db.commit()
        logger.info("Default teams and user accounts seeded successfully.")


__all__ = [
    "DEFAULT_TEAMS",
    "DEFAULT_USERS",
    "password_hash_helper",
    "seed_default_users",
]

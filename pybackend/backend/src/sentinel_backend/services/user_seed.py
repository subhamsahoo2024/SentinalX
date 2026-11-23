import logging
from datetime import UTC, datetime

from pwdlib import PasswordHash
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sentinel_backend.models.user import UserAccount

logger = logging.getLogger(__name__)

password_hash_helper = PasswordHash.recommended()

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
    """Inserts demo user accounts if the user_accounts table is empty.

    Accounts seeded:
    - admin@sentinel.local (Priya Nair (Admin), role: admin)
    - approver@sentinel.local (Arjun Mehta (Approver), role: approver)
    - operator@sentinel.local (Devika Rao (Operator), role: operator)
    - viewer@sentinel.local (Rohan Das (Auditor), role: viewer)

    All accounts are seeded with password 'sentinel123' hashed via Argon2.
    """
    result = await db.execute(select(UserAccount).limit(1))
    if result.scalar_one_or_none() is not None:
        return

    logger.info("Seeding default user accounts with Argon2 password hashes...")
    hashed_pwd = password_hash_helper.hash("sentinel123")
    now_utc = datetime.now(UTC)

    for user_info in DEFAULT_USERS:
        account = UserAccount(
            user_id=user_info["user_id"],
            email=user_info["email"],
            display_name=user_info["display_name"],
            password_hash=hashed_pwd,
            role=user_info["role"],
            created_at=now_utc,
        )
        db.add(account)

    await db.commit()
    logger.info("Default user accounts seeded successfully.")


__all__ = ["DEFAULT_USERS", "password_hash_helper", "seed_default_users"]


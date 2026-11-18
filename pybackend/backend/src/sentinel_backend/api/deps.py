import secrets
from fastapi import Header, HTTPException, status

from sentinel_backend.config import settings


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


__all__ = ["verify_api_key"]


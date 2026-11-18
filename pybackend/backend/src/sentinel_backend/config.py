from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


def _find_env_file() -> tuple[str, ...]:
    candidates: list[str] = [".env"]
    current = Path(__file__).resolve()
    for parent in current.parents:
        env_candidate = parent / ".env"
        if env_candidate.is_file():
            candidates.append(str(env_candidate))
    return tuple(candidates)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_find_env_file(),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    DATABASE_URL: str = (
        "postgresql+asyncpg://sentinel:sentinel_dev@localhost:5432/sentinel_x"
    )
    REDIS_URL: str = "redis://localhost:6379/0"
    SENTINEL_API_KEY: str = "dev-secret-key"


settings = Settings()

__all__ = ["Settings", "settings"]


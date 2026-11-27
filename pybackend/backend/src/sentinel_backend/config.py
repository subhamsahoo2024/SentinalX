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

    DATABASE_URL: str
    REDIS_URL: str
    SENTINEL_API_KEY: str

    # Auth & JWT Configuration
    JWT_SECRET: str = "sentinel-dev-jwt-secret-change-in-prod-32chars"
    JWT_EXPIRE_MINUTES: int = 480
    ALLOW_DEV_HEADERS: bool = True
    ENABLE_DEMO_SANDBOX: bool = True
    INITIAL_ADMIN_EMAIL: str | None = None
    INITIAL_ADMIN_PASSWORD: str | None = None

    @property
    def effective_allow_dev_headers(self) -> bool:
        return self.ALLOW_DEV_HEADERS and self.ENABLE_DEMO_SANDBOX

    # Deterministic anomaly detection & watchdog thresholds
    LOOP_THRESHOLD_COUNT: int
    LOOP_WINDOW_SECONDS: int
    RUN_TOKEN_BUDGET: int
    RUN_STALL_TIMEOUT_SEC: int
    INGEST_RATE_LIMIT_PER_MIN: int = 600
    RETENTION_DAYS: int = 30


settings = Settings()

__all__ = ["Settings", "settings"]


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

    # Deterministic anomaly detection & watchdog thresholds
    LOOP_THRESHOLD_COUNT: int
    LOOP_WINDOW_SECONDS: int
    RUN_TOKEN_BUDGET: int
    RUN_STALL_TIMEOUT_SEC: int


settings = Settings()

__all__ = ["Settings", "settings"]


import os
from pathlib import Path

from dotenv import load_dotenv

_env_loaded = False


def find_env_file() -> Path | None:
    """Traverse parent directories to discover root .env configuration file."""
    current = Path(__file__).resolve()
    for parent in [current] + list(current.parents):
        env_candidate = parent / ".env"
        if env_candidate.is_file():
            return env_candidate
    cwd_candidate = Path.cwd() / ".env"
    if cwd_candidate.is_file():
        return cwd_candidate
    return None


def load_sdk_env() -> tuple[str, str]:
    """Load Sentinel SDK configuration strictly from .env without fallback default values.

    Returns:
        (sentinel_url, sentinel_api_key)

    Raises:
        ValueError: if SENTINEL_URL or SENTINEL_API_KEY is not defined in .env.
    """
    global _env_loaded
    if not _env_loaded:
        env_path = find_env_file()
        if env_path is not None:
            load_dotenv(dotenv_path=env_path)
        _env_loaded = True

    url = os.getenv("SENTINEL_URL")
    if not url:
        raise ValueError(
            "Missing SENTINEL_URL in environment or .env file. "
            "Configuration must be specified in .env (e.g. SENTINEL_URL=http://127.0.0.1:8000)."
        )

    api_key = os.getenv("SENTINEL_API_KEY")
    if not api_key:
        raise ValueError(
            "Missing SENTINEL_API_KEY in environment or .env file. "
            "Configuration must be specified in .env (e.g. SENTINEL_API_KEY=dev-secret-key)."
        )

    if "localhost" in url:
        url = url.replace("localhost", "127.0.0.1")

    return url.rstrip("/"), api_key


__all__ = ["find_env_file", "load_sdk_env"]


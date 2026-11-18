import dataclasses
from typing import Any

SENSITIVE_KEY_SUBSTRINGS: tuple[str, ...] = (
    "token",
    "secret",
    "password",
    "passwd",
    "api_key",
    "apikey",
    "authorization",
    "credential",
    "ssn",
    "private_key",
)


def is_sensitive_key(key: Any) -> bool:
    """Check if a dictionary key matches any sensitive substring (case-insensitive)."""
    key_str = str(key).lower()
    return any(sub in key_str for sub in SENSITIVE_KEY_SUBSTRINGS)


def redact_payload(
    data: Any,
    max_str_len: int = 2000,
    seen: set[int] | None = None,
) -> Any:
    """Recursively traverses dicts, lists, and tuples to redact sensitive data

    and truncate strings longer than max_str_len with '...[TRUNCATED]'.
    """
    if seen is None:
        seen = set()

    if isinstance(data, str):
        if len(data) > max_str_len:
            return data[:max_str_len] + "...[TRUNCATED]"
        return data

    if isinstance(data, (int, float, bool)) or data is None:
        return data

    obj_id = id(data)
    if obj_id in seen:
        return "[CIRCULAR]"

    if isinstance(data, dict):
        seen.add(obj_id)
        try:
            redacted_dict: dict[Any, Any] = {}
            for k, v in data.items():
                if is_sensitive_key(k):
                    redacted_dict[k] = "[REDACTED]"
                else:
                    redacted_dict[k] = redact_payload(
                        v, max_str_len=max_str_len, seen=seen
                    )
            return redacted_dict
        finally:
            seen.remove(obj_id)

    if isinstance(data, list):
        seen.add(obj_id)
        try:
            return [
                redact_payload(item, max_str_len=max_str_len, seen=seen)
                for item in data
            ]
        finally:
            seen.remove(obj_id)

    if isinstance(data, tuple):
        seen.add(obj_id)
        try:
            return tuple(
                redact_payload(item, max_str_len=max_str_len, seen=seen)
                for item in data
            )
        finally:
            seen.remove(obj_id)

    if isinstance(data, (set, frozenset)):
        seen.add(obj_id)
        try:
            return [
                redact_payload(item, max_str_len=max_str_len, seen=seen)
                for item in data
            ]
        finally:
            seen.remove(obj_id)

    if hasattr(data, "model_dump") and callable(data.model_dump):
        seen.add(obj_id)
        try:
            return redact_payload(
                data.model_dump(), max_str_len=max_str_len, seen=seen
            )
        finally:
            seen.remove(obj_id)

    if dataclasses.is_dataclass(data) and not isinstance(data, type):
        seen.add(obj_id)
        try:
            return redact_payload(
                dataclasses.asdict(data), max_str_len=max_str_len, seen=seen
            )
        finally:
            seen.remove(obj_id)

    data_dict = getattr(data, "__dict__", None)
    if isinstance(data_dict, dict) and not isinstance(data, type):
        seen.add(obj_id)
        try:
            return redact_payload(data_dict, max_str_len=max_str_len, seen=seen)
        finally:
            seen.remove(obj_id)

    # For any other objects, safely stringify and apply truncation
    s = str(data)
    if len(s) > max_str_len:
        return s[:max_str_len] + "...[TRUNCATED]"
    return s


__all__ = [
    "SENSITIVE_KEY_SUBSTRINGS",
    "is_sensitive_key",
    "redact_payload",
]

import secrets
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from sentinel_backend.db.session import Base

DEFAULT_WEBHOOK_EVENT_TYPES: tuple[str, ...] = (
    "APPROVAL_REQUIRED",
    "CASCADE_FAILURE",
    "LOOP_DETECTED",
    "BUDGET_EXCEEDED",
    "RUN_STALLED",
)


def _generate_signing_secret() -> str:
    return f"whsec_{secrets.token_hex(24)}"


class WebhookEndpoint(Base):
    __tablename__ = "webhook_endpoints"

    webhook_id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    team: Mapped[str | None] = mapped_column(String, index=True, nullable=True)
    url: Mapped[str] = mapped_column(String, nullable=False)
    signing_secret: Mapped[str] = mapped_column(
        String,
        default=_generate_signing_secret,
        nullable=False,
    )
    event_types: Mapped[list[str]] = mapped_column(
        JSONB,
        default=lambda: list(DEFAULT_WEBHOOK_EVENT_TYPES),
        server_default=(
            '["APPROVAL_REQUIRED", "CASCADE_FAILURE", "LOOP_DETECTED", '
            '"BUDGET_EXCEEDED", "RUN_STALLED"]'
        ),
        nullable=False,
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        server_default="true",
        nullable=False,
    )
    last_status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_triggered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
        nullable=False,
    )

    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("signing_secret", _generate_signing_secret())
        kwargs.setdefault("event_types", list(DEFAULT_WEBHOOK_EVENT_TYPES))
        kwargs.setdefault("enabled", True)
        kwargs.setdefault("created_at", datetime.now(UTC))
        super().__init__(**kwargs)

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from sentinel_backend.db.session import Base


class AuditEvent(Base):
    __tablename__ = "audit_events"

    audit_id: Mapped[str] = mapped_column(String, primary_key=True)
    actor_id: Mapped[str] = mapped_column(String, nullable=False)
    actor_role: Mapped[str] = mapped_column(String, nullable=False)
    action: Mapped[str] = mapped_column(String, nullable=False)
    target_type: Mapped[str] = mapped_column(String, nullable=False)
    target_id: Mapped[str] = mapped_column(String, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}", nullable=False
    )
    prev_hash: Mapped[str] = mapped_column(
        String(64), default="GENESIS", server_default="GENESIS", nullable=False
    )
    entry_hash: Mapped[str] = mapped_column(
        String(64), default="", server_default="", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("prev_hash", "GENESIS")
        kwargs.setdefault("entry_hash", "")
        super().__init__(**kwargs)


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
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


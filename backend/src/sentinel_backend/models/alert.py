from datetime import datetime
from typing import TYPE_CHECKING, Any
from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from sentinel_backend.db.session import Base

if TYPE_CHECKING:
    from sentinel_backend.models.run import Run


class Alert(Base):
    __tablename__ = "alerts"

    alert_id: Mapped[str] = mapped_column(String, primary_key=True)
    run_id: Mapped[str] = mapped_column(
        String, ForeignKey("runs.run_id", ondelete="CASCADE"), index=True, nullable=False
    )
    origin_span_id: Mapped[str | None] = mapped_column(String, nullable=True)
    rule_id: Mapped[str] = mapped_column(String, nullable=False)
    severity: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    evidence: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}", nullable=False
    )
    impacted_span_ids: Mapped[list[Any]] = mapped_column(
        JSONB, default=list, server_default="[]", nullable=False
    )
    acknowledged: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    run: Mapped["Run"] = relationship("Run", back_populates="alerts")


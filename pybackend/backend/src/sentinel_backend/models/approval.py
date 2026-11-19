from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from sentinel_backend.db.session import Base

if TYPE_CHECKING:
    from sentinel_backend.models.run import Run
    from sentinel_backend.models.span import Span


class Approval(Base):
    __tablename__ = "approvals"

    approval_id: Mapped[str] = mapped_column(String, primary_key=True)
    run_id: Mapped[str] = mapped_column(
        String, ForeignKey("runs.run_id", ondelete="CASCADE"), index=True, nullable=False
    )
    span_id: Mapped[str] = mapped_column(
        String, ForeignKey("spans.span_id", ondelete="CASCADE"), unique=True, nullable=False
    )
    agent_id: Mapped[str] = mapped_column(String, nullable=False)
    tool_name: Mapped[str] = mapped_column(String, nullable=False)
    sanitized_args: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}", nullable=False
    )
    risk_level: Mapped[str] = mapped_column(String, nullable=False)
    policy_reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String, default="PENDING", server_default="PENDING", nullable=False
    )
    decided_by: Mapped[str | None] = mapped_column(String, nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    run: Mapped["Run"] = relationship("Run", back_populates="approvals")
    span: Mapped["Span"] = relationship("Span", back_populates="approval")


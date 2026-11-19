from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from sentinel_backend.db.session import Base

if TYPE_CHECKING:
    from sentinel_backend.models.approval import Approval
    from sentinel_backend.models.run import Run


class Span(Base):
    __tablename__ = "spans"

    span_id: Mapped[str] = mapped_column(String, primary_key=True)
    trace_id: Mapped[str] = mapped_column(String, index=True, nullable=False)
    parent_span_id: Mapped[str | None] = mapped_column(
        String, index=True, nullable=True
    )
    run_id: Mapped[str] = mapped_column(
        String, ForeignKey("runs.run_id", ondelete="CASCADE"), index=True, nullable=False
    )
    agent_id: Mapped[str] = mapped_column(String, index=True, nullable=False)
    attempt_number: Mapped[int] = mapped_column(
        Integer, default=1, server_default="1", nullable=False
    )
    span_type: Mapped[str] = mapped_column(String, nullable=False)
    operation_name: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    model_provider: Mapped[str | None] = mapped_column(String, nullable=True)
    model_name: Mapped[str | None] = mapped_column(String, nullable=True)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cached_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    direct_cost_usd: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 6), nullable=True
    )
    cost_basis: Mapped[str] = mapped_column(
        String, default="UNKNOWN", server_default="UNKNOWN", nullable=False
    )
    is_root_cause: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )
    error_class: Mapped[str | None] = mapped_column(String, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    attributes: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}", nullable=False
    )

    run: Mapped["Run"] = relationship("Run", back_populates="spans")
    approval: Mapped["Approval | None"] = relationship(
        "Approval", back_populates="span", uselist=False, cascade="all, delete-orphan"
    )


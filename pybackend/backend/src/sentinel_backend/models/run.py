from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from sentinel_backend.db.session import Base

if TYPE_CHECKING:
    from sentinel_backend.models.agent import Agent
    from sentinel_backend.models.alert import Alert
    from sentinel_backend.models.approval import Approval
    from sentinel_backend.models.span import Span


class Run(Base):
    __tablename__ = "runs"

    run_id: Mapped[str] = mapped_column(String, primary_key=True)
    trace_id: Mapped[str] = mapped_column(
        String, unique=True, index=True, nullable=False
    )
    root_agent_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("agents.agent_id", ondelete="SET NULL"), nullable=True
    )
    team: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_event_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    total_tokens: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    total_cost_usd: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 6), nullable=True
    )
    cost_status: Mapped[str] = mapped_column(
        String, default="UNKNOWN", server_default="UNKNOWN", nullable=False
    )

    root_agent: Mapped["Agent | None"] = relationship("Agent", back_populates="runs")
    spans: Mapped[list["Span"]] = relationship(
        "Span", back_populates="run", cascade="all, delete-orphan"
    )
    approvals: Mapped[list["Approval"]] = relationship(
        "Approval", back_populates="run", cascade="all, delete-orphan"
    )
    alerts: Mapped[list["Alert"]] = relationship(
        "Alert", back_populates="run", cascade="all, delete-orphan"
    )


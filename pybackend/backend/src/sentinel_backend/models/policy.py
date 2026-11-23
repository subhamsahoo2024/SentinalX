from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, Integer, Numeric, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from sentinel_backend.db.session import Base


class Policy(Base):
    __tablename__ = "policies"

    policy_id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    team: Mapped[str | None] = mapped_column(String, nullable=True)
    agent_id: Mapped[str | None] = mapped_column(String, nullable=True)
    max_tokens: Mapped[int] = mapped_column(
        Integer, default=5000, server_default="5000", nullable=False
    )
    max_cost_usd: Mapped[Decimal] = mapped_column(
        Numeric(10, 4),
        default=Decimal("0.5000"),
        server_default="0.5000",
        nullable=False,
    )
    loop_threshold: Mapped[int] = mapped_column(
        Integer, default=3, server_default="3", nullable=False
    )
    loop_window_sec: Mapped[int] = mapped_column(
        Integer, default=30, server_default="30", nullable=False
    )
    auto_block_on_budget: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )
    protected_tools: Mapped[list[str]] = mapped_column(
        JSONB, default=list, server_default="[]", nullable=False
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true", nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )


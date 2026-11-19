from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from sentinel_backend.db.session import Base

if TYPE_CHECKING:
    from sentinel_backend.models.run import Run


class Agent(Base):
    __tablename__ = "agents"

    agent_id: Mapped[str] = mapped_column(String, primary_key=True)
    display_name: Mapped[str] = mapped_column(String, nullable=False)
    framework: Mapped[str] = mapped_column(String, nullable=False)
    team: Mapped[str] = mapped_column(String, nullable=False)
    environment: Mapped[str] = mapped_column(
        String, default="development", server_default="development", nullable=False
    )
    declared_tools: Mapped[list[Any]] = mapped_column(
        JSONB, default=list, server_default="[]", nullable=False
    )
    status: Mapped[str] = mapped_column(String, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    runs: Mapped[list["Run"]] = relationship("Run", back_populates="root_agent")


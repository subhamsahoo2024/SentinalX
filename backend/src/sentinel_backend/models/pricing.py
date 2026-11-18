from datetime import datetime
from decimal import Decimal
from sqlalchemy import DateTime, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from sentinel_backend.db.session import Base


class PricingVersion(Base):
    __tablename__ = "pricing_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider: Mapped[str] = mapped_column(String, nullable=False)
    model_name: Mapped[str] = mapped_column(String, nullable=False)
    version_tag: Mapped[str] = mapped_column(String, nullable=False)
    input_rate_per_1m: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    output_rate_per_1m: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    effective_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


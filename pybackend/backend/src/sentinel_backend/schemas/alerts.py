from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AlertDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    alert_id: str
    run_id: str
    origin_span_id: str | None = None
    rule_id: str
    severity: str
    title: str
    evidence: dict[str, Any] = Field(default_factory=dict)
    impacted_span_ids: list[str] = Field(default_factory=list)
    acknowledged: bool = False
    created_at: datetime


__all__ = ["AlertDTO"]


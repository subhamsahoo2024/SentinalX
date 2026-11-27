from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

WebhookEventType = Literal[
    "APPROVAL_REQUIRED",
    "CASCADE_FAILURE",
    "LOOP_DETECTED",
    "BUDGET_EXCEEDED",
    "RUN_STALLED",
]


class WebhookCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    team: str | None = None
    url: str
    event_types: list[WebhookEventType]


class WebhookUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    team: str | None = None
    url: str | None = None
    event_types: list[WebhookEventType] | None = None
    enabled: bool | None = None


class WebhookDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    webhook_id: str
    name: str
    team: str | None = None
    url: str
    signing_secret: str
    event_types: list[WebhookEventType]
    enabled: bool
    last_status_code: int | None = None
    last_triggered_at: datetime | None = None
    created_at: datetime


__all__ = [
    "WebhookCreate",
    "WebhookDTO",
    "WebhookEventType",
    "WebhookUpdate",
]


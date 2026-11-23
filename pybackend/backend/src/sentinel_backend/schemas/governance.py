from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ApprovalRequestCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    span_id: str
    agent_id: str
    tool_name: str
    sanitized_args: dict[str, Any] = Field(default_factory=dict)
    risk_level: str = "HIGH"
    policy_reason: str


class ApprovalDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["APPROVED", "REJECTED"]
    comment: str | None = None


class ApprovalDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    approval_id: str
    run_id: str
    span_id: str
    agent_id: str
    tool_name: str
    sanitized_args: dict[str, Any] = Field(default_factory=dict)
    risk_level: str
    policy_reason: str
    status: str
    decided_by: str | None = None
    decided_at: datetime | None = None
    comment: str | None = None
    created_at: datetime


class AuditEventDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    audit_id: str
    actor_id: str
    actor_role: str
    action: str
    target_type: str
    target_id: str
    payload: dict[str, Any] = Field(default_factory=dict)
    prev_hash: str = "GENESIS"
    entry_hash: str = ""
    created_at: datetime

    @field_validator("prev_hash", mode="before")
    @classmethod
    def set_prev_hash(cls, v: Any) -> str:
        return v if (v is not None and v != "") else "GENESIS"

    @field_validator("entry_hash", mode="before")
    @classmethod
    def set_entry_hash(cls, v: Any) -> str:
        return v if v is not None else ""


__all__ = [
    "ApprovalDTO",
    "ApprovalDecisionRequest",
    "ApprovalRequestCreate",
    "AuditEventDTO",
]

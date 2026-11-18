from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class SpanType(StrEnum):
    AGENT = "AGENT"
    LLM = "LLM"
    TOOL = "TOOL"
    APPROVAL = "APPROVAL"


class SpanStatus(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    TIMED_OUT = "TIMED_OUT"
    CANCELLED = "CANCELLED"
    STALLED = "STALLED"


class CostBasis(StrEnum):
    EXACT = "EXACT"
    ESTIMATED = "ESTIMATED"
    UNKNOWN = "UNKNOWN"


class ModelInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str | None = None
    name: str | None = None


class TokenUsage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input_tokens: int | None = None
    output_tokens: int | None = None
    cached_tokens: int | None = None


class CostInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    amount_usd: float | None = None
    currency: str = "USD"
    basis: CostBasis = CostBasis.UNKNOWN
    pricing_version: str | None = None


class ErrorInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    error_class: str
    message: str
    stack_summary: str | None = None


class CanonicalEventV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    event_id: str
    trace_id: str
    span_id: str
    parent_span_id: str | None = None
    run_id: str
    agent_id: str
    agent_name: str | None = None
    team: str = "default"
    framework: str = "custom"
    attempt_number: int = 1
    span_type: SpanType
    operation_name: str
    status: SpanStatus
    started_at: datetime
    ended_at: datetime | None = None
    model: ModelInfo | None = None
    usage: TokenUsage | None = None
    cost: CostInfo = Field(default_factory=CostInfo)
    error: ErrorInfo | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)


class TelemetryBatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    events: list[CanonicalEventV1]


__all__ = [
    "CanonicalEventV1",
    "CostBasis",
    "CostInfo",
    "ErrorInfo",
    "ModelInfo",
    "SpanStatus",
    "SpanType",
    "TelemetryBatchRequest",
    "TokenUsage",
]

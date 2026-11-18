from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from sentinel_sdk.schema import (
    CanonicalEventV1,
    CostBasis,
    CostInfo,
    ErrorInfo,
    ModelInfo,
    SpanStatus,
    SpanType,
    TelemetryBatchRequest,
    TokenUsage,
)


class RunSummaryDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    trace_id: str | None = None
    agent_id: str
    agent_name: str | None = None
    team: str = "default"
    framework: str = "custom"
    status: SpanStatus
    started_at: datetime
    ended_at: datetime | None = None
    duration_ms: float | None = None
    total_spans: int = 0
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    error_count: int = 0


class LineageNodeDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    span_id: str
    parent_span_id: str | None = None
    agent_id: str
    attempt_number: int = 1
    span_type: str
    operation_name: str
    status: str
    started_at: datetime
    ended_at: datetime | None = None
    duration_ms: float | None = None
    model_provider: str | None = None
    model_name: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    direct_cost_usd: float | None = None
    cost_basis: str = "UNKNOWN"
    is_root_cause: bool = False
    error_class: str | None = None
    error_message: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)


class LineageEdgeDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    source: str
    target: str
    is_failed_path: bool = False


class LineageGraphDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    trace_id: str
    status: str
    nodes: list[LineageNodeDTO] = Field(default_factory=list)
    edges: list[LineageEdgeDTO] = Field(default_factory=list)
    orphan_span_ids: list[str] = Field(default_factory=list)


class SpanDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    span_id: str
    trace_id: str
    parent_span_id: str | None = None
    run_id: str
    agent_id: str
    attempt_number: int = 1
    span_type: str
    operation_name: str
    status: str
    started_at: datetime
    ended_at: datetime | None = None
    duration_ms: float | None = None
    model_provider: str | None = None
    model_name: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    cached_tokens: int | None = None
    direct_cost_usd: float | None = None
    cost_basis: str = "UNKNOWN"
    is_root_cause: bool = False
    error_class: str | None = None
    error_message: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)


__all__ = [
    "CanonicalEventV1",
    "CostBasis",
    "CostInfo",
    "ErrorInfo",
    "LineageEdgeDTO",
    "LineageGraphDTO",
    "LineageNodeDTO",
    "ModelInfo",
    "RunSummaryDTO",
    "SpanDTO",
    "SpanStatus",
    "SpanType",
    "TelemetryBatchRequest",
    "TokenUsage",
]

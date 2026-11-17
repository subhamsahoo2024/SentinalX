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
    run_id: str | None = None
    agent_id: str | None = None
    agent_name: str | None = None
    span_type: SpanType
    operation_name: str
    status: SpanStatus
    started_at: datetime | None = None
    ended_at: datetime | None = None
    duration_ms: float | None = None
    model: ModelInfo | None = None
    usage: TokenUsage | None = None
    cost: CostInfo = Field(default_factory=CostInfo)
    error: ErrorInfo | None = None
    data: dict[str, Any] = Field(default_factory=dict)


class LineageEdgeDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    source: str
    target: str
    edge_type: str | None = None
    label: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)


class LineageGraphDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    nodes: list[LineageNodeDTO] = Field(default_factory=list)
    edges: list[LineageEdgeDTO] = Field(default_factory=list)
    root_span_id: str | None = None


__all__ = [
    # Re-exported from sentinel_sdk.schema
    "SpanType",
    "SpanStatus",
    "CostBasis",
    "ModelInfo",
    "TokenUsage",
    "CostInfo",
    "ErrorInfo",
    "CanonicalEventV1",
    "TelemetryBatchRequest",
    # Response DTOs
    "RunSummaryDTO",
    "LineageNodeDTO",
    "LineageEdgeDTO",
    "LineageGraphDTO",
]


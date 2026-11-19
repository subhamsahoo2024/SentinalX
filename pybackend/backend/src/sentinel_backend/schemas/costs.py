from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class PricingVersionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str
    model_name: str
    version_tag: str
    input_rate_per_1m: float
    output_rate_per_1m: float


class PricingVersionDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    provider: str
    model_name: str
    version_tag: str
    input_rate_per_1m: float
    output_rate_per_1m: float
    effective_from: datetime


class CostBreakdownItemDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    key: str
    label: str
    run_count: int
    span_count: int
    input_tokens: int
    output_tokens: int
    total_cost_usd: float | None
    unknown_spans_count: int


class CostSummaryDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    total_known_cost_usd: float
    total_tokens: int
    unknown_usage_spans_count: int
    by_agent: list[CostBreakdownItemDTO] = Field(default_factory=list)
    by_team: list[CostBreakdownItemDTO] = Field(default_factory=list)
    by_model: list[CostBreakdownItemDTO] = Field(default_factory=list)
    by_run: list[CostBreakdownItemDTO] = Field(default_factory=list)


__all__ = [
    "CostBreakdownItemDTO",
    "CostSummaryDTO",
    "PricingVersionCreate",
    "PricingVersionDTO",
]


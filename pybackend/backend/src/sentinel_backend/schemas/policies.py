from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class PolicyCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    team: str | None = None
    agent_id: str | None = None
    max_tokens: int = 5000
    max_cost_usd: float = 0.50
    loop_threshold: int = 3
    loop_window_sec: int = 30
    auto_block_on_budget: bool = False
    protected_tools: list[str] = Field(default_factory=list)
    enabled: bool = True
    policy_id: str | None = None


class PolicyUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    team: str | None = None
    agent_id: str | None = None
    max_tokens: int | None = None
    max_cost_usd: float | None = None
    loop_threshold: int | None = None
    loop_window_sec: int | None = None
    auto_block_on_budget: bool | None = None
    protected_tools: list[str] | None = None
    enabled: bool | None = None


class PolicyDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    policy_id: str
    name: str
    team: str | None = None
    agent_id: str | None = None
    max_tokens: int
    max_cost_usd: float
    loop_threshold: int
    loop_window_sec: int
    auto_block_on_budget: bool
    protected_tools: list[str] = Field(default_factory=list)
    enabled: bool
    updated_at: datetime


__all__ = [
    "PolicyCreate",
    "PolicyDTO",
    "PolicyUpdate",
]


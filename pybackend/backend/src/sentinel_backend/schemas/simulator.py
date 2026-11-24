from typing import Literal

from pydantic import BaseModel, ConfigDict

ScenarioName = Literal[
    "normal",
    "hitl",
    "loop",
    "slow_loop",
    "cascade",
    "budget",
    "stall",
]


class SimulatorLaunchRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    scenario: ScenarioName
    team: str = "it-ops"
    live_llm: bool = False


class SimulatorLaunchResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    run_id: str
    scenario: ScenarioName
    team: str
    status: Literal["LAUNCHED"] = "LAUNCHED"


__all__ = [
    "ScenarioName",
    "SimulatorLaunchRequest",
    "SimulatorLaunchResponse",
]


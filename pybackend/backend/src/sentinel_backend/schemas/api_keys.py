from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ApiKeyCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    team: str


class ApiKeyDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    key_id: str
    name: str
    team: str
    key_prefix: str
    created_by: str
    last_used_at: datetime | None = None
    revoked_at: datetime | None = None
    created_at: datetime


class ApiKeyCreatedDTO(ApiKeyDTO):
    raw_key: str


__all__ = [
    "ApiKeyCreate",
    "ApiKeyCreatedDTO",
    "ApiKeyDTO",
]


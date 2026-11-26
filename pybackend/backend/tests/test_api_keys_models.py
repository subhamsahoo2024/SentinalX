from datetime import UTC, datetime

import pytest
from pydantic import ValidationError
from sentinel_backend.db.session import Base
from sentinel_backend.models import ApiKey
from sentinel_backend.schemas import ApiKeyCreate, ApiKeyCreatedDTO, ApiKeyDTO


def test_api_key_model_and_metadata():
    assert "api_keys" in Base.metadata.tables
    table = Base.metadata.tables["api_keys"]
    assert table.c.team.index is True
    assert table.c.key_hash.unique is True
    assert table.c.key_hash.index is True
    assert table.c.key_prefix.type.length == 16
    assert table.c.key_hash.type.length == 64

    now = datetime.now(UTC)
    api_key = ApiKey(
        key_id="key_9a2f4b1c8d0e",
        name="Fraud Detection Prod Cluster",
        team="fraud-detection",
        key_prefix="sk_live_9a2f",
        key_hash="a" * 64,
        created_by="admin@acme.io",
        created_at=now,
    )
    assert api_key.key_id == "key_9a2f4b1c8d0e"
    assert api_key.name == "Fraud Detection Prod Cluster"
    assert api_key.team == "fraud-detection"
    assert api_key.key_prefix == "sk_live_9a2f"
    assert api_key.key_hash == "a" * 64
    assert api_key.created_by == "admin@acme.io"
    assert api_key.last_used_at is None
    assert api_key.revoked_at is None
    assert api_key.created_at == now


def test_api_key_schemas():
    create = ApiKeyCreate(
        name="Customer Support Prod",
        team="customer-support",
    )
    assert create.name == "Customer Support Prod"
    assert create.team == "customer-support"

    with pytest.raises(ValidationError):
        ApiKeyCreate(name="Bad", team="it-ops", extra_field="nope")  # type: ignore[call-arg]

    now = datetime.now(UTC)
    api_key = ApiKey(
        key_id="key_123456789abc",
        name="IT Ops Runner",
        team="it-ops",
        key_prefix="sk_live_1234",
        key_hash="b" * 64,
        created_by="admin@acme.io",
        last_used_at=now,
        revoked_at=None,
        created_at=now,
    )

    dto = ApiKeyDTO.model_validate(api_key)
    assert dto.key_id == "key_123456789abc"
    assert dto.name == "IT Ops Runner"
    assert dto.team == "it-ops"
    assert dto.key_prefix == "sk_live_1234"
    assert dto.created_by == "admin@acme.io"
    assert dto.last_used_at == now
    assert dto.revoked_at is None
    assert dto.created_at == now
    assert not hasattr(dto, "key_hash")

    created_dto = ApiKeyCreatedDTO(
        **dto.model_dump(),
        raw_key="sk_live_1234567890abcdef",
    )
    assert created_dto.raw_key == "sk_live_1234567890abcdef"
    assert created_dto.key_id == "key_123456789abc"


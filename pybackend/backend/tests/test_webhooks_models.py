from datetime import UTC, datetime

import pytest
from pydantic import ValidationError
from sentinel_backend.config import Settings, settings
from sentinel_backend.db.session import Base
from sentinel_backend.models import WebhookEndpoint
from sentinel_backend.schemas import (
    WebhookCreate,
    WebhookDTO,
    WebhookUpdate,
)


def test_config_rate_limit_and_retention_defaults(monkeypatch: pytest.MonkeyPatch):
    assert settings.INGEST_RATE_LIMIT_PER_MIN == 600
    assert settings.RETENTION_DAYS == 30

    monkeypatch.setenv("INGEST_RATE_LIMIT_PER_MIN", "1200")
    monkeypatch.setenv("RETENTION_DAYS", "90")
    custom = Settings()  # type: ignore[call-arg]
    assert custom.INGEST_RATE_LIMIT_PER_MIN == 1200
    assert custom.RETENTION_DAYS == 90


def test_webhook_endpoint_model_and_metadata():
    assert "webhook_endpoints" in Base.metadata.tables
    table = Base.metadata.tables["webhook_endpoints"]
    assert table.c.team.index is True
    assert table.c.team.nullable is True
    assert table.c.signing_secret.nullable is False
    assert table.c.enabled.nullable is False

    endpoint = WebhookEndpoint(
        webhook_id="wh_8f3a1b2c9d0e",
        name="Fraud On-Call PagerDuty",
        team="fraud-detection",
        url="https://hooks.example.com/pagerduty",
    )
    assert endpoint.webhook_id == "wh_8f3a1b2c9d0e"
    assert endpoint.name == "Fraud On-Call PagerDuty"
    assert endpoint.team == "fraud-detection"
    assert endpoint.url == "https://hooks.example.com/pagerduty"
    assert endpoint.signing_secret.startswith("whsec_")
    assert len(endpoint.signing_secret) == 54
    assert endpoint.event_types == [
        "APPROVAL_REQUIRED",
        "CASCADE_FAILURE",
        "LOOP_DETECTED",
        "BUDGET_EXCEEDED",
        "RUN_STALLED",
    ]
    assert endpoint.enabled is True
    assert endpoint.last_status_code is None
    assert endpoint.last_triggered_at is None
    assert endpoint.created_at is not None


def test_webhook_schemas():
    create = WebhookCreate(
        name="Org Incident Slack",
        url="https://hooks.slack.com/services/T000/B000/XXX",
        event_types=["CASCADE_FAILURE", "BUDGET_EXCEEDED"],
    )
    assert create.team is None
    assert create.event_types == ["CASCADE_FAILURE", "BUDGET_EXCEEDED"]

    with pytest.raises(ValidationError):
        WebhookCreate(
            name="Invalid Event",
            url="https://hooks.example.com/test",
            event_types=["UNKNOWN_EVENT"],  # type: ignore[list-item]
        )

    update = WebhookUpdate(enabled=False, name="Paused PagerDuty")
    assert update.enabled is False
    assert update.name == "Paused PagerDuty"
    assert update.team is None

    now = datetime.now(UTC)
    endpoint = WebhookEndpoint(
        webhook_id="wh_112233445566",
        name="Org Incident Slack",
        team=None,
        url="https://hooks.slack.com/services/T000/B000/XXX",
        signing_secret="whsec_abcdef123456",
        event_types=["APPROVAL_REQUIRED", "RUN_STALLED"],
        enabled=True,
        last_status_code=200,
        last_triggered_at=now,
        created_at=now,
    )
    dto = WebhookDTO.model_validate(endpoint)
    assert dto.webhook_id == "wh_112233445566"
    assert dto.team is None
    assert dto.signing_secret == "whsec_abcdef123456"
    assert dto.event_types == ["APPROVAL_REQUIRED", "RUN_STALLED"]
    assert dto.last_status_code == 200
    assert dto.last_triggered_at == now
    assert dto.created_at == now


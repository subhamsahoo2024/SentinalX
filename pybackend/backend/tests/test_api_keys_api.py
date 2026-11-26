import hashlib
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
from sentinel_backend.api.deps import (
    ActorContext,
    IngestContext,
    require_admin,
    verify_ingest_auth,
)
from sentinel_backend.config import settings
from sentinel_backend.db.session import get_db
from sentinel_backend.main import app
from sentinel_backend.models.api_key import ApiKey
from sentinel_backend.models.audit import AuditEvent
from sentinel_backend.models.run import Run
from sentinel_backend.models.team import Team
from sentinel_backend.services.ingestion import ingest_telemetry_batch
from sentinel_sdk.schema import CanonicalEventV1, SpanStatus, SpanType


class InMemoryApiKeyDB:
    """Lightweight async in-memory DB double for API key CRUD and ingest auth tests."""

    def __init__(
        self,
        teams: list[Team] | None = None,
        api_keys: list[ApiKey] | None = None,
        events: list[AuditEvent] | None = None,
    ) -> None:
        self.teams: list[Team] = list(teams or [])
        self.api_keys: list[ApiKey] = list(api_keys or [])
        self.events: list[AuditEvent] = list(events or [])

    async def get(self, model: type[Any], key: str) -> Any:
        if model is Team:
            return next((t for t in self.teams if t.team_id == key), None)
        if model is ApiKey:
            return next((k for k in self.api_keys if k.key_id == key), None)
        return None

    async def execute(self, stmt: Any) -> Any:
        stmt_str = str(stmt).lower()
        res = MagicMock()

        if "from audit_events" in stmt_str:
            sorted_events = sorted(
                self.events,
                key=lambda x: (x.created_at, x.audit_id),
                reverse="desc" in stmt_str,
            )
            res.scalar_one_or_none.return_value = (
                sorted_events[0] if sorted_events else None
            )
            return res

        if "from api_keys" in stmt_str:
            matched = list(self.api_keys)
            if hasattr(stmt, "_where_criteria") and stmt._where_criteria:
                for crit in stmt._where_criteria:
                    col_name = getattr(getattr(crit, "left", None), "name", None)
                    right = getattr(crit, "right", None)
                    val = getattr(right, "value", None)
                    crit_str = str(crit).lower()
                    if col_name == "key_hash" and val is not None:
                        matched = [k for k in matched if k.key_hash == str(val)]
                    elif col_name == "revoked_at" and "is null" in crit_str:
                        matched = [k for k in matched if k.revoked_at is None]

            sorted_keys = sorted(
                matched,
                key=lambda k: k.created_at,
                reverse="desc" in stmt_str,
            )
            res.scalar_one_or_none.return_value = (
                sorted_keys[0] if sorted_keys else None
            )
            res.scalars.return_value.all.return_value = sorted_keys
            return res

        res.scalar_one_or_none.return_value = None
        res.scalars.return_value.all.return_value = []
        return res

    def add(self, obj: Any) -> None:
        if isinstance(obj, ApiKey):
            self.api_keys.append(obj)
        elif isinstance(obj, AuditEvent):
            self.events.append(obj)

    async def flush(self) -> None:
        return None

    async def commit(self) -> None:
        return None

    async def refresh(self, _obj: Any) -> None:
        return None


@pytest.mark.asyncio
async def test_api_keys_forbidden_for_demo_admin():
    fake_db = InMemoryApiKeyDB()
    demo_admin = ActorContext(
        actor_id="admin@sentinel.local",
        actor_role="admin",
        is_demo=True,
    )
    app.dependency_overrides[get_db] = lambda: fake_db
    app.dependency_overrides[require_admin] = lambda: demo_admin

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/api-keys")
            assert resp.status_code == 403
            create_resp = await client.post(
                "/api/api-keys",
                json={"name": "Cluster", "team": "fraud-detection"},
            )
            assert create_resp.status_code == 403
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_create_list_and_revoke_api_keys():
    now = datetime.now(UTC)
    existing_key = ApiKey(
        key_id="key_older000001",
        name="Older Key",
        team="it-ops",
        key_prefix="sk_live_0001",
        key_hash="c" * 64,
        created_by="admin@acme.io",
        created_at=now - timedelta(hours=2),
    )
    fake_db = InMemoryApiKeyDB(
        teams=[
            Team(team_id="fraud-detection", display_name="Fraud Detection"),
            Team(team_id="it-ops", display_name="IT Operations"),
            Team(team_id="demo-sandbox", display_name="Demo Sandbox"),
        ],
        api_keys=[existing_key],
    )
    org_admin = ActorContext(
        actor_id="admin@acme.io",
        actor_role="admin",
        is_demo=False,
    )
    app.dependency_overrides[get_db] = lambda: fake_db
    app.dependency_overrides[require_admin] = lambda: org_admin

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Unknown team -> 404
            missing_team_resp = await client.post(
                "/api/api-keys",
                json={"name": "Missing", "team": "does-not-exist"},
            )
            assert missing_team_resp.status_code == 404

            # demo-sandbox -> 400
            demo_team_resp = await client.post(
                "/api/api-keys",
                json={"name": "Sandbox", "team": "demo-sandbox"},
            )
            assert demo_team_resp.status_code == 400

            # Valid create
            create_resp = await client.post(
                "/api/api-keys",
                json={
                    "name": "Fraud Detection Prod Cluster",
                    "team": "fraud-detection",
                },
            )
            assert create_resp.status_code == 201
            created = create_resp.json()
            assert created["key_id"].startswith("key_")
            assert created["name"] == "Fraud Detection Prod Cluster"
            assert created["team"] == "fraud-detection"
            assert created["raw_key"].startswith("sk_live_")
            assert created["key_prefix"] == created["raw_key"][:12]
            assert created["created_by"] == "admin@acme.io"
            assert "key_hash" not in created

            # Stored hash matches SHA-256 of raw_key
            stored = next(
                k for k in fake_db.api_keys if k.key_id == created["key_id"]
            )
            expected_hash = hashlib.sha256(
                created["raw_key"].encode("utf-8")
            ).hexdigest()
            assert stored.key_hash == expected_hash
            assert fake_db.events[-1].action == "API_KEY_CREATED"
            assert fake_db.events[-1].target_id == created["key_id"]

            # List ordered created_at DESC and never exposes key_hash
            list_resp = await client.get("/api/api-keys")
            assert list_resp.status_code == 200
            listed = list_resp.json()
            assert [item["key_id"] for item in listed] == [
                created["key_id"],
                "key_older000001",
            ]
            assert all("key_hash" not in item for item in listed)
            assert all("raw_key" not in item for item in listed)

            # Revoke missing -> 404
            revoke_missing = await client.delete("/api/api-keys/key_missing")
            assert revoke_missing.status_code == 404

            # Soft-revoke created key
            revoke_resp = await client.delete(f"/api/api-keys/{created['key_id']}")
            assert revoke_resp.status_code == 200
            assert revoke_resp.json() == {
                "status": "revoked",
                "key_id": created["key_id"],
            }
            assert stored.revoked_at is not None
            assert fake_db.events[-1].action == "API_KEY_REVOKED"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_verify_ingest_auth_team_key_and_revocation():
    raw_key = "sk_live_testkey1234567890"
    digest = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
    active_key = ApiKey(
        key_id="key_fraud01",
        name="Fraud Prod",
        team="fraud-detection",
        key_prefix=raw_key[:12],
        key_hash=digest,
        created_by="admin@acme.io",
        created_at=datetime.now(UTC),
    )
    fake_db = InMemoryApiKeyDB(api_keys=[active_key])

    ctx = await verify_ingest_auth(
        x_api_key=raw_key,
        authorization=None,
        db=fake_db,  # type: ignore[arg-type]
    )
    assert ctx == IngestContext(
        team="fraud-detection",
        key_id="key_fraud01",
        is_demo=False,
    )
    assert active_key.last_used_at is not None

    # Also works via Authorization: Bearer <token>
    ctx_bearer = await verify_ingest_auth(
        x_api_key=None,
        authorization=f"Bearer {raw_key}",
        db=fake_db,  # type: ignore[arg-type]
    )
    assert ctx_bearer.team == "fraud-detection"

    # Revoked key raises 401
    active_key.revoked_at = datetime.now(UTC)
    with pytest.raises(HTTPException) as exc_info:
        await verify_ingest_auth(
            x_api_key=raw_key,
            authorization=None,
            db=fake_db,  # type: ignore[arg-type]
        )
    assert exc_info.value.status_code == 401

    # Demo env key rejected when ENABLE_DEMO_SANDBOX is False
    with patch.object(settings, "ENABLE_DEMO_SANDBOX", False):
        with pytest.raises(HTTPException) as disabled_exc:
            await verify_ingest_auth(
                x_api_key=settings.SENTINEL_API_KEY,
                authorization=None,
                db=fake_db,  # type: ignore[arg-type]
            )
        assert disabled_exc.value.status_code == 401


@pytest.mark.asyncio
async def test_telemetry_endpoints_pass_enforced_team_and_ingestion_overwrites():
    raw_key = "sk_live_prod_fraud_key"
    digest = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
    active_key = ApiKey(
        key_id="key_fraud02",
        name="Fraud Prod",
        team="fraud-detection",
        key_prefix=raw_key[:12],
        key_hash=digest,
        created_by="admin@acme.io",
        created_at=datetime.now(UTC),
    )
    fake_db = InMemoryApiKeyDB(api_keys=[active_key])
    app.dependency_overrides[get_db] = lambda: fake_db

    now = datetime.now(UTC)
    payload = {
        "events": [
            {
                "schema_version": "1.0",
                "event_id": "evt_spoof_1",
                "trace_id": "a" * 32,
                "span_id": "span_spoof_1",
                "run_id": "run_spoof_1",
                "agent_id": "fraud-agent",
                "team": "it-ops",
                "span_type": "AGENT",
                "operation_name": "score_tx",
                "status": "RUNNING",
                "started_at": now.isoformat(),
            }
        ]
    }

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            with patch(
                "sentinel_backend.api.telemetry.ingest_telemetry_batch",
                new_callable=AsyncMock,
            ) as mock_ingest:
                mock_ingest.return_value = {"accepted": 1, "run_ids": ["run_spoof_1"]}
                resp = await client.post(
                    "/api/telemetry/events",
                    json=payload,
                    headers={"X-API-Key": raw_key},
                )
                assert resp.status_code == 202
                mock_ingest.assert_awaited_once()
                assert mock_ingest.call_args.kwargs["enforced_team"] == "fraud-detection"
    finally:
        app.dependency_overrides.clear()

    # Verify ingest_telemetry_batch overwrites spoofed event.team before DB writes
    spoofed_event = CanonicalEventV1(
        event_id="evt_spoof_2",
        trace_id="b" * 32,
        span_id="span_spoof_2",
        run_id="run_spoof_2",
        agent_id="fraud-agent",
        team="it-ops",
        span_type=SpanType.AGENT,
        operation_name="score_tx",
        status=SpanStatus.RUNNING,
        started_at=now,
    )

    mock_db = AsyncMock()
    tokens_mock = MagicMock()
    tokens_mock.scalar_one.return_value = 0
    run_select_mock = MagicMock()
    run_select_mock.scalar_one_or_none.return_value = Run(
        run_id="run_spoof_2",
        trace_id="b" * 32,
        root_agent_id="fraud-agent",
        team="fraud-detection",
        status="RUNNING",
        started_at=now,
        last_event_at=now,
        total_tokens=0,
        cost_status="UNKNOWN",
    )

    def execute_side_effect(stmt: Any) -> Any:
        stmt_str = str(stmt).lower()
        if "sum(" in stmt_str:
            return tokens_mock
        if "from runs" in stmt_str:
            return run_select_mock
        return MagicMock()

    mock_db.execute.side_effect = execute_side_effect

    with (
        patch(
            "sentinel_backend.services.ingestion.calculate_run_costs",
            new_callable=AsyncMock,
        ),
        patch(
            "sentinel_backend.services.ingestion.evaluate_run_anomalies",
            new_callable=AsyncMock,
        ),
        patch(
            "sentinel_backend.services.ingestion.publish_event",
            new_callable=AsyncMock,
        ),
    ):
        await ingest_telemetry_batch(
            mock_db,
            [spoofed_event],
            enforced_team="fraud-detection",
        )

    assert spoofed_event.team == "fraud-detection"
    executed_params = [
        call.args[0].compile().params
        for call in mock_db.execute.call_args_list
        if hasattr(call.args[0], "compile")
    ]
    assert any(p.get("team") == "fraud-detection" for p in executed_params)
    assert not any(p.get("team") == "it-ops" for p in executed_params)


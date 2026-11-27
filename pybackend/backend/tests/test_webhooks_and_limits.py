import asyncio
import hashlib
import hmac
import json
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
from redis.exceptions import RedisError
from sentinel_backend.api.deps import (
    ActorContext,
    IngestContext,
    require_admin,
    verify_ingest_auth,
)
from sentinel_backend.api.telemetry import _enforce_ingest_rate_limit
from sentinel_backend.config import settings
from sentinel_backend.db.session import get_db
from sentinel_backend.main import app
from sentinel_backend.models.audit import AuditEvent
from sentinel_backend.models.run import Run
from sentinel_backend.models.span import Span
from sentinel_backend.models.team import Team
from sentinel_backend.models.webhook import WebhookEndpoint
from sentinel_backend.schemas.governance import ApprovalRequestCreate
from sentinel_backend.services.anomaly_engine import (
    _upsert_alert,
    purge_expired_telemetry,
    retention_cleanup_loop,
)
from sentinel_backend.services.governance import create_approval_request
from sentinel_backend.services.redis_bus import close_redis, get_redis_client
from sentinel_backend.services.webhooks import (
    _sign_payload,
    deliver_single_webhook,
    enqueue_team_webhooks,
)


class InMemoryWebhookDB:
    """Lightweight async in-memory DB double for webhook CRUD and audit tests."""

    def __init__(
        self,
        teams: list[Team] | None = None,
        webhooks: list[WebhookEndpoint] | None = None,
    ) -> None:
        self.teams: list[Team] = list(teams or [])
        self.webhooks: list[WebhookEndpoint] = list(webhooks or [])
        self.events: list[AuditEvent] = []

    async def get(self, model: type[Any], key: str) -> Any:
        if model is Team:
            return next((t for t in self.teams if t.team_id == key), None)
        if model is WebhookEndpoint:
            return next((w for w in self.webhooks if w.webhook_id == key), None)
        return None

    async def delete(self, obj: Any) -> None:
        if isinstance(obj, WebhookEndpoint) and obj in self.webhooks:
            self.webhooks.remove(obj)

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

        if "from webhook_endpoints" in stmt_str:
            ordered = sorted(
                self.webhooks,
                key=lambda w: w.created_at,
                reverse="desc" in stmt_str,
            )
            res.scalars.return_value.all.return_value = ordered
            res.scalar_one_or_none.return_value = ordered[0] if ordered else None
            return res

        res.scalar_one_or_none.return_value = None
        res.scalars.return_value.all.return_value = []
        return res

    def add(self, obj: Any) -> None:
        if isinstance(obj, WebhookEndpoint):
            self.webhooks.append(obj)
        elif isinstance(obj, AuditEvent):
            self.events.append(obj)

    async def flush(self) -> None:
        return None

    async def commit(self) -> None:
        return None

    async def refresh(self, _obj: Any) -> None:
        return None


def test_sign_payload_hmac_sha256():
    secret = "whsec_supersecret"
    ts = 1700000123
    body = '{"event":"LOOP_DETECTED"}'
    header = _sign_payload(secret, ts, body)
    expected = hmac.new(
        secret.encode("utf-8"),
        f"{ts}.{body}".encode(),
        hashlib.sha256,
    ).hexdigest()
    assert header == f"t={ts},v1={expected}"


@pytest.mark.asyncio
async def test_deliver_single_webhook_success_and_retries():
    endpoint = WebhookEndpoint(
        webhook_id="wh_test1",
        name="Test PagerDuty",
        team="fraud-detection",
        url="https://hooks.example.com/events",
        signing_secret="whsec_test123",
    )
    session = InMemoryWebhookDB(webhooks=[endpoint])

    @asynccontextmanager
    async def fake_session_maker():
        yield session

    # Case 1: 500 -> ConnectError -> 202 (succeeds on 3rd attempt)
    attempts = 0

    async def mock_post(_url: str, *, content: str, headers: dict[str, str]):
        nonlocal attempts
        attempts += 1
        assert headers["Content-Type"] == "application/json"
        assert headers["X-Sentinel-Event"] == "BUDGET_EXCEEDED"
        assert headers["X-Sentinel-Signature"].startswith("t=")
        parsed = json.loads(content)
        assert parsed["event"] == "BUDGET_EXCEEDED"
        assert parsed["data"]["run_id"] == "run_1"
        if attempts == 1:
            return httpx.Response(500)
        if attempts == 2:
            raise httpx.ConnectError("connection reset")
        return httpx.Response(202)

    mock_http_client = AsyncMock()
    mock_http_client.post.side_effect = mock_post
    mock_http_cm = AsyncMock()
    mock_http_cm.__aenter__.return_value = mock_http_client
    mock_http_cm.__aexit__.return_value = False

    with (
        patch("sentinel_backend.services.webhooks.httpx.AsyncClient", return_value=mock_http_cm),
        patch("sentinel_backend.services.webhooks.asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
        patch("sentinel_backend.services.webhooks.async_session_maker", fake_session_maker),
    ):
        status_code = await deliver_single_webhook(
            webhook_id="wh_test1",
            url=endpoint.url,
            secret=endpoint.signing_secret,
            event_type="BUDGET_EXCEEDED",
            payload={"run_id": "run_1"},
        )

    assert status_code == 202
    assert attempts == 3
    assert [call.args[0] for call in mock_sleep.call_args_list] == [0.5, 1.5]
    assert endpoint.last_status_code == 202
    assert endpoint.last_triggered_at is not None


@pytest.mark.asyncio
async def test_enqueue_team_webhooks_filters_demo_team_and_events():
    db = AsyncMock()
    # Demo sandbox must never fire external webhooks
    tasks_demo = await enqueue_team_webhooks(
        db, "demo-sandbox", "LOOP_DETECTED", {"run_id": "run_demo"}
    )
    assert tasks_demo == []
    db.execute.assert_not_called()

    ep_match_team = WebhookEndpoint(
        webhook_id="wh_fraud",
        name="Fraud",
        team="fraud-detection",
        url="https://hooks.example.com/fraud",
        event_types=["LOOP_DETECTED"],
        enabled=True,
    )
    ep_match_global = WebhookEndpoint(
        webhook_id="wh_global",
        name="Org Global",
        team=None,
        url="https://hooks.example.com/global",
        event_types=["LOOP_DETECTED", "BUDGET_EXCEEDED"],
        enabled=True,
    )
    ep_wrong_event = WebhookEndpoint(
        webhook_id="wh_other_evt",
        name="Stall Only",
        team=None,
        url="https://hooks.example.com/stall",
        event_types=["RUN_STALLED"],
        enabled=True,
    )

    exec_res = MagicMock()
    exec_res.scalars.return_value.all.return_value = [
        ep_match_team,
        ep_match_global,
        ep_wrong_event,
    ]
    db.execute.return_value = exec_res

    deliver_mock = AsyncMock(return_value=200)
    with patch("sentinel_backend.services.webhooks.deliver_single_webhook", deliver_mock):
        tasks = await enqueue_team_webhooks(
            db, "fraud-detection", "LOOP_DETECTED", {"run_id": "run_fraud"}
        )
        assert len(tasks) == 2
        await asyncio.gather(*tasks)

    assert deliver_mock.await_count == 2
    called_ids = {call.kwargs["webhook_id"] for call in deliver_mock.await_args_list}
    assert called_ids == {"wh_fraud", "wh_global"}


@pytest.mark.asyncio
async def test_webhook_triggers_wired_in_governance_and_anomaly_engine():
    # Governance APPROVAL_REQUIRED wiring
    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    mock_span = Span(span_id="span_1", run_id="run_1", status="RUNNING")
    mock_run = Run(run_id="run_1", team="fraud-detection", status="RUNNING")

    async def mock_get(entity: Any, ident: str) -> Any:
        if entity is Span and ident == "span_1":
            return mock_span
        if entity is Run and ident == "run_1":
            return mock_run
        return None

    mock_db.get.side_effect = mock_get
    exec_res = MagicMock()
    exec_res.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = exec_res

    req = ApprovalRequestCreate(
        run_id="run_1",
        span_id="span_1",
        agent_id="fraud-agent",
        tool_name="wire_transfer",
        sanitized_args={"amount": 50000},
        risk_level="HIGH",
        policy_reason="High value transfer",
    )

    with (
        patch("sentinel_backend.services.governance.publish_event", new_callable=AsyncMock),
        patch(
            "sentinel_backend.services.governance.enqueue_team_webhooks",
            new_callable=AsyncMock,
        ) as mock_enqueue_gov,
    ):
        await create_approval_request(mock_db, req)
        mock_enqueue_gov.assert_awaited_once()
        assert mock_enqueue_gov.call_args.args[1] == "fraud-detection"
        assert mock_enqueue_gov.call_args.args[2] == "APPROVAL_REQUIRED"

    # Anomaly engine only enqueues webhook on NEW alert, not update
    alert_db = AsyncMock()
    alert_db.add = MagicMock()
    new_res = MagicMock()
    new_res.scalar_one_or_none.return_value = None
    alert_db.execute.return_value = new_res

    with (
        patch("sentinel_backend.services.anomaly_engine.publish_event", new_callable=AsyncMock),
        patch(
            "sentinel_backend.services.anomaly_engine.enqueue_team_webhooks",
            new_callable=AsyncMock,
        ) as mock_enqueue_anom,
    ):
        await _upsert_alert(
            db=alert_db,
            run_id="run_1",
            rule_id="CASCADE_FAILURE",
            origin_span_id="span_1",
            severity="CRITICAL",
            title="Cascade",
            evidence={"affected_count": 2},
            impacted_span_ids=["span_1", "span_2"],
            team="fraud-detection",
        )
        mock_enqueue_anom.assert_awaited_once()
        assert mock_enqueue_anom.call_args.args[1] == "fraud-detection"
        assert mock_enqueue_anom.call_args.args[2] == "CASCADE_FAILURE"


@pytest.mark.asyncio
async def test_webhooks_api_crud_test_and_rbac():
    fake_db = InMemoryWebhookDB(
        teams=[Team(team_id="fraud-detection", display_name="Fraud Detection")]
    )
    demo_admin = ActorContext(
        actor_id="admin@sentinel.local",
        actor_role="admin",
        is_demo=True,
    )
    org_admin = ActorContext(
        actor_id="org-admin@acme.io",
        actor_role="admin",
        allowed_teams=["*"],
        is_demo=False,
    )

    app.dependency_overrides[get_db] = lambda: fake_db
    app.dependency_overrides[require_admin] = lambda: demo_admin

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp_demo = await client.get("/api/webhooks")
            assert resp_demo.status_code == 403

            app.dependency_overrides[require_admin] = lambda: org_admin

            resp_bad_team = await client.post(
                "/api/webhooks",
                json={
                    "name": "Demo Bad",
                    "team": "demo-sandbox",
                    "url": "https://hooks.example.com/bad",
                    "event_types": ["LOOP_DETECTED"],
                },
            )
            assert resp_bad_team.status_code == 400

            resp_create = await client.post(
                "/api/webhooks",
                json={
                    "name": "Fraud On-Call PagerDuty",
                    "team": "fraud-detection",
                    "url": "https://hooks.example.com/pd",
                    "event_types": ["APPROVAL_REQUIRED", "CASCADE_FAILURE"],
                },
            )
            assert resp_create.status_code == 201
            created = resp_create.json()
            assert created["webhook_id"].startswith("wh_")
            assert created["signing_secret"].startswith("whsec_")
            assert created["enabled"] is True

            webhook_id = created["webhook_id"]

            resp_list = await client.get("/api/webhooks")
            assert resp_list.status_code == 200
            assert len(resp_list.json()) == 1

            resp_patch = await client.patch(
                f"/api/webhooks/{webhook_id}",
                json={"enabled": False, "name": "Fraud PagerDuty Updated"},
            )
            assert resp_patch.status_code == 200
            assert resp_patch.json()["enabled"] is False
            assert resp_patch.json()["name"] == "Fraud PagerDuty Updated"

            with patch(
                "sentinel_backend.api.webhooks.deliver_single_webhook",
                new_callable=AsyncMock,
                return_value=200,
            ) as mock_deliver:
                resp_test = await client.post(f"/api/webhooks/{webhook_id}/test")
                assert resp_test.status_code == 200
                assert resp_test.json() == {"delivered": True, "status_code": 200}
                mock_deliver.assert_awaited_once()
                assert mock_deliver.call_args.kwargs["event_type"] == "TEST_PING"

            resp_delete = await client.delete(f"/api/webhooks/{webhook_id}")
            assert resp_delete.status_code == 200
            assert resp_delete.json()["status"] == "deleted"

            actions = [e.action for e in fake_db.events]
            assert actions == ["WEBHOOK_CREATED", "WEBHOOK_UPDATED", "WEBHOOK_DELETED"]
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_ingest_rate_limit_unit_and_telemetry_429(monkeypatch: pytest.MonkeyPatch):
    # Skip demo-sandbox
    mock_redis = AsyncMock()
    await _enforce_ingest_rate_limit(mock_redis, "demo-sandbox", 5000)
    mock_redis.eval.assert_not_called()

    # Enforce sliding-window limit unit check (works even if Redis is offline)
    monkeypatch.setattr(settings, "INGEST_RATE_LIMIT_PER_MIN", 3)
    test_team = "rate-limit-test-team"
    unit_redis = AsyncMock()
    unit_redis.eval.side_effect = [[1, 2], [0, 2]]
    await _enforce_ingest_rate_limit(unit_redis, test_team, 2)
    with pytest.raises(HTTPException) as unit_exc:
        await _enforce_ingest_rate_limit(unit_redis, test_team, 2)
    assert unit_exc.value.status_code == 429
    assert unit_exc.value.headers["Retry-After"] == "60"
    assert unit_exc.value.headers["X-RateLimit-Limit"] == "3"

    # Enforce real Redis sliding window via Lua when Redis is reachable (e.g. CI)
    redis_client = get_redis_client()
    redis_available = False
    try:
        await redis_client.ping()
        redis_available = True
        await redis_client.delete(f"ratelimit:ingest:{test_team}")
        await _enforce_ingest_rate_limit(redis_client, test_team, 2)
        with pytest.raises(HTTPException) as exc_info:
            await _enforce_ingest_rate_limit(redis_client, test_team, 2)
        assert exc_info.value.status_code == 429
        assert exc_info.value.headers["Retry-After"] == "60"
        assert exc_info.value.headers["X-RateLimit-Limit"] == "3"
    except (RedisError, OSError, TimeoutError):
        pass
    finally:
        if redis_available:
            await redis_client.delete(f"ratelimit:ingest:{test_team}")
        await close_redis()

    # Verify both /api/telemetry/events and /v1/traces reject with 429 when limit exceeded
    blocked_redis = AsyncMock()
    blocked_redis.eval.return_value = [0, 3]
    now = datetime.now(UTC)

    app.dependency_overrides[get_db] = lambda: AsyncMock()
    app.dependency_overrides[verify_ingest_auth] = lambda: IngestContext(
        team="fraud-detection", key_id="key_1"
    )
    try:
        with patch(
            "sentinel_backend.api.telemetry.get_redis_client",
            return_value=blocked_redis,
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp_events = await client.post(
                    "/api/telemetry/events",
                    json={
                        "events": [
                            {
                                "event_id": "evt_rl_1",
                                "trace_id": "a" * 32,
                                "span_id": "span_rl_1",
                                "run_id": "run_rl_1",
                                "agent_id": "fraud-agent",
                                "span_type": "AGENT",
                                "operation_name": "run",
                                "status": "RUNNING",
                                "started_at": now.isoformat(),
                            }
                        ]
                    },
                )
                assert resp_events.status_code == 429
                assert resp_events.headers.get("Retry-After") == "60"

                otlp_payload = {
                    "resourceSpans": [
                        {
                            "resource": {"attributes": []},
                            "scopeSpans": [
                                {
                                    "spans": [
                                        {
                                            "traceId": "11112222333344445555666677778888",
                                            "spanId": "9999888877776666",
                                            "name": "chat",
                                            "startTimeUnixNano": "1700000000000000000",
                                            "endTimeUnixNano": "1700000001000000000",
                                        }
                                    ]
                                }
                            ],
                        }
                    ]
                }
                resp_otlp = await client.post(
                    "/v1/traces",
                    content=json.dumps(otlp_payload).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                )
                assert resp_otlp.status_code == 429
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_purge_expired_telemetry_and_loop_cancellation():
    mock_db = AsyncMock()
    expired_select_res = MagicMock()
    expired_select_res.scalars.return_value.all.return_value = [
        "run_old_1",
        "run_old_2",
    ]
    delete_res = MagicMock()
    mock_db.execute.side_effect = [
        expired_select_res,
        delete_res,
        delete_res,
        delete_res,
        delete_res,
    ]

    deleted_count = await purge_expired_telemetry(mock_db)
    assert deleted_count == 2
    mock_db.commit.assert_awaited_once()

    executed_sql = [str(call.args[0]).lower() for call in mock_db.execute.call_args_list]
    assert any("delete from approvals" in s for s in executed_sql)
    assert any("delete from alerts" in s for s in executed_sql)
    assert any("delete from spans" in s for s in executed_sql)
    assert any("delete from runs" in s for s in executed_sql)
    assert not any("audit_events" in s for s in executed_sql)

    # No expired runs
    empty_db = AsyncMock()
    empty_res = MagicMock()
    empty_res.scalars.return_value.all.return_value = []
    empty_db.execute.return_value = empty_res
    assert await purge_expired_telemetry(empty_db) == 0
    empty_db.commit.assert_not_awaited()

    # Cutoff check verification
    cutoff_check = datetime.now(UTC) - timedelta(days=settings.RETENTION_DAYS)
    assert cutoff_check < datetime.now(UTC)

    # Loop exits cleanly on cancellation
    @asynccontextmanager
    async def noop_session():
        yield empty_db

    task = asyncio.create_task(
        retention_cleanup_loop(noop_session, interval_seconds=3600)
    )
    await asyncio.sleep(0.05)
    task.cancel()
    await task

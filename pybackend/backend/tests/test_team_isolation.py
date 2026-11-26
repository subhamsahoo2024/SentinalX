from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import jwt
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
from sentinel_backend.api.deps import (
    ActorContext,
    apply_team_scope,
    assert_team_access,
    get_current_actor,
)
from sentinel_backend.config import settings
from sentinel_backend.db.session import get_db
from sentinel_backend.main import app
from sentinel_backend.models.alert import Alert
from sentinel_backend.models.approval import Approval
from sentinel_backend.models.policy import Policy
from sentinel_backend.models.run import Run
from sentinel_backend.schemas.governance import ApprovalRequestCreate
from sentinel_backend.services.anomaly_engine import evaluate_run_anomalies
from sentinel_backend.services.governance import create_approval_request
from sentinel_backend.services.ingestion import ingest_telemetry_batch
from sentinel_sdk.schema import CanonicalEventV1, SpanStatus, SpanType
from sqlalchemy import select
from sqlalchemy.dialects import postgresql


def _make_jwt(actor: ActorContext) -> str:
    return jwt.encode(
        {
            "sub": actor.actor_id,
            "email": actor.actor_id,
            "name": actor.display_name or actor.actor_id,
            "role": actor.actor_role,
            "allowed_teams": actor.allowed_teams,
            "is_demo": actor.is_demo,
            "exp": datetime.now(UTC) + timedelta(minutes=30),
        },
        settings.JWT_SECRET,
        algorithm="HS256",
    )


def _compile_sql(stmt: Any) -> str:
    return str(
        stmt.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )


def test_apply_team_scope_variants():
    demo = ActorContext(
        actor_id="approver@sentinel.local",
        actor_role="approver",
        allowed_teams=["demo-sandbox"],
        is_demo=True,
    )
    org_admin = ActorContext(
        actor_id="admin@acme.io",
        actor_role="admin",
        allowed_teams=["*"],
        is_demo=False,
    )
    fraud_op = ActorContext(
        actor_id="analyst@acme.io",
        actor_role="operator",
        allowed_teams=["fraud-detection"],
        is_demo=False,
    )

    demo_sql = _compile_sql(apply_team_scope(select(Run), Run.team, demo))
    assert "runs.team = 'demo-sandbox'" in demo_sql

    admin_sql = _compile_sql(apply_team_scope(select(Run), Run.team, org_admin))
    assert "runs.team != 'demo-sandbox'" in admin_sql

    fraud_sql = _compile_sql(apply_team_scope(select(Run), Run.team, fraud_op))
    assert "runs.team IN ('fraud-detection')" in fraud_sql
    assert "runs.team != 'demo-sandbox'" in fraud_sql


def test_assert_team_access_isolation():
    demo = ActorContext(
        actor_id="approver@sentinel.local",
        actor_role="approver",
        allowed_teams=["demo-sandbox"],
        is_demo=True,
    )
    org_admin = ActorContext(
        actor_id="admin@acme.io",
        actor_role="admin",
        allowed_teams=["*"],
        is_demo=False,
    )
    fraud_op = ActorContext(
        actor_id="analyst@acme.io",
        actor_role="operator",
        allowed_teams=["fraud-detection"],
        is_demo=False,
    )

    assert_team_access("demo-sandbox", demo)
    with pytest.raises(HTTPException) as exc_demo:
        assert_team_access("fraud-detection", demo)
    assert exc_demo.value.status_code == 403

    assert_team_access("fraud-detection", org_admin)
    with pytest.raises(HTTPException) as exc_admin:
        assert_team_access("demo-sandbox", org_admin)
    assert exc_admin.value.status_code == 403

    assert_team_access("fraud-detection", fraud_op)
    for forbidden_team in ("it-ops", "demo-sandbox"):
        with pytest.raises(HTTPException) as exc_op:
            assert_team_access(forbidden_team, fraud_op)
        assert exc_op.value.status_code == 403


@pytest.mark.asyncio
async def test_rest_endpoints_enforce_team_scope_and_isolation():
    now = datetime.now(UTC)
    fraud_run = Run(
        run_id="run_fraud_1",
        trace_id="a" * 32,
        root_agent_id="fraud-agent",
        team="fraud-detection",
        status="RUNNING",
        started_at=now,
        last_event_at=now,
    )
    demo_run = Run(
        run_id="run_demo_1",
        trace_id="b" * 32,
        root_agent_id="demo-agent",
        team="demo-sandbox",
        status="RUNNING",
        started_at=now,
        last_event_at=now,
    )
    fraud_alert = Alert(
        alert_id="alert_fraud_1",
        run_id="run_fraud_1",
        rule_id="LOOP_DETECTED",
        severity="HIGH",
        title="Loop",
        evidence={},
        impacted_span_ids=[],
        acknowledged=False,
        created_at=now,
    )
    fraud_approval = Approval(
        approval_id="apr_fraud_1",
        run_id="run_fraud_1",
        span_id="span_fraud_1",
        agent_id="fraud-agent",
        tool_name="wire_transfer",
        sanitized_args={},
        risk_level="HIGH",
        policy_reason="Protected",
        status="PENDING",
        created_at=now,
    )

    mock_db = AsyncMock()
    executed_sql: list[str] = []

    async def fake_get(entity: Any, ident: Any, *args: Any, **kwargs: Any) -> Any:
        if entity is Run:
            return {"run_fraud_1": fraud_run, "run_demo_1": demo_run}.get(ident)
        if entity is Alert and ident == "alert_fraud_1":
            return fraud_alert
        if entity is Approval and ident == "apr_fraud_1":
            return fraud_approval
        return None

    async def fake_execute(stmt: Any) -> MagicMock:
        executed_sql.append(_compile_sql(stmt))
        res = MagicMock()
        res.scalars.return_value.all.return_value = []
        res.all.return_value = []
        res.scalar_one_or_none.return_value = fraud_approval
        return res

    mock_db.get.side_effect = fake_get
    mock_db.execute.side_effect = fake_execute

    it_ops_approver = ActorContext(
        actor_id="ops-lead@acme.io",
        actor_role="approver",
        allowed_teams=["it-ops"],
        is_demo=False,
    )
    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[get_current_actor] = lambda: it_ops_approver

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # 1. Cross-team run & demo run forbidden on GET /cancel /lineage
            for path in (
                "/api/runs/run_fraud_1",
                "/api/runs/run_fraud_1/lineage",
                "/api/runs/run_demo_1",
            ):
                resp = await client.get(path)
                assert resp.status_code == 403

            assert (await client.post("/api/runs/run_fraud_1/cancel")).status_code == 403
            assert (await client.patch("/api/alerts/alert_fraud_1/ack")).status_code == 403
            assert (
                await client.post(
                    "/api/approvals/apr_fraud_1/decision",
                    json={"decision": "APPROVED", "comment": "nope"},
                )
            ).status_code == 403

            # 2. List/summary endpoints filter SQL by it-ops and exclude demo-sandbox
            executed_sql.clear()
            assert (await client.get("/api/agents")).status_code == 200
            assert "agents.team IN ('it-ops')" in executed_sql[-1]
            assert "agents.team != 'demo-sandbox'" in executed_sql[-1]

            executed_sql.clear()
            assert (await client.get("/api/agents/slos")).status_code == 200
            assert any("agents.team IN ('it-ops')" in s for s in executed_sql)

            executed_sql.clear()
            assert (await client.get("/api/runs")).status_code == 200
            assert "runs.team IN ('it-ops')" in executed_sql[-1]

            executed_sql.clear()
            assert (await client.get("/api/alerts")).status_code == 200
            assert "JOIN runs ON alerts.run_id = runs.run_id" in executed_sql[-1]
            assert "runs.team IN ('it-ops')" in executed_sql[-1]

            executed_sql.clear()
            assert (await client.get("/api/approvals")).status_code == 200
            assert "JOIN runs ON approvals.run_id = runs.run_id" in executed_sql[-1]
            assert "runs.team IN ('it-ops')" in executed_sql[-1]

            executed_sql.clear()
            assert (await client.get("/api/audit-events")).status_code == 200
            assert "'@sentinel.local'" in executed_sql[-1]
            assert "'demo-sandbox'" in executed_sql[-1]

            executed_sql.clear()
            assert (await client.get("/api/costs/summary")).status_code == 200
            assert any("runs.team IN ('it-ops')" in s for s in executed_sql)
            assert any("agents.team IN ('it-ops')" in s for s in executed_sql)

            executed_sql.clear()
            assert (await client.get("/api/policies")).status_code == 200
            assert "policies.team IS NULL" in executed_sql[-1]
            assert "policies.team IN ('it-ops')" in executed_sql[-1]
            assert "policies.team != 'demo-sandbox'" in executed_sql[-1]
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_redis_pub_sub_payloads_include_team():
    now = datetime.now(UTC)
    run = Run(
        run_id="run_pub_1",
        trace_id="c" * 32,
        root_agent_id="fraud-agent",
        team="fraud-detection",
        status="RUNNING",
        started_at=now,
        last_event_at=now,
        total_tokens=99999,
    )
    event = CanonicalEventV1(
        event_id="evt_pub_1",
        trace_id="c" * 32,
        span_id="span_pub_1",
        run_id="run_pub_1",
        agent_id="fraud-agent",
        team="fraud-detection",
        span_type=SpanType.TOOL,
        operation_name="charge_card",
        status=SpanStatus.RUNNING,
        started_at=now,
    )

    mock_db = AsyncMock()
    tokens_res = MagicMock()
    tokens_res.scalar_one.return_value = 0
    run_res = MagicMock()
    run_res.scalar_one_or_none.return_value = run

    def exec_side_effect(stmt: Any) -> MagicMock:
        s = str(stmt).lower()
        if "sum(" in s:
            return tokens_res
        if "from runs" in s:
            return run_res
        res = MagicMock()
        res.scalar_one_or_none.return_value = None
        res.scalars.return_value.all.return_value = []
        return res

    mock_db.execute.side_effect = exec_side_effect

    with (
        patch("sentinel_backend.services.ingestion.calculate_run_costs", new_callable=AsyncMock),
        patch("sentinel_backend.services.ingestion.evaluate_run_anomalies", new_callable=AsyncMock),
        patch("sentinel_backend.services.ingestion.publish_event", new_callable=AsyncMock) as mock_ing_pub,
    ):
        await ingest_telemetry_batch(mock_db, [event], enforced_team="fraud-detection")
        fleet_calls = [c for c in mock_ing_pub.call_args_list if c.args[1] == "FLEET_UPDATED"]
        run_calls = [c for c in mock_ing_pub.call_args_list if c.args[1] == "RUN_UPDATED"]
        assert fleet_calls[0].args[2]["team"] == "fraud-detection"
        assert run_calls[0].args[2]["team"] == "fraud-detection"

    # ALERT_CREATED payload includes team
    alert_db = AsyncMock()
    alert_db.add = MagicMock()
    alert_db.get.return_value = run
    policy = Policy(
        policy_id="pol_test",
        name="Default",
        team=None,
        agent_id=None,
        max_tokens=100,
        max_cost_usd=10,
        loop_threshold=3,
        loop_window_sec=30,
        auto_block_on_budget=False,
        protected_tools=[],
        enabled=True,
        updated_at=now,
    )
    empty_res = MagicMock()
    empty_res.scalar_one_or_none.return_value = None
    empty_res.scalars.return_value.all.return_value = []
    alert_db.execute.return_value = empty_res
    with (
        patch(
            "sentinel_backend.services.anomaly_engine.resolve_effective_policy",
            new_callable=AsyncMock,
            return_value=policy,
        ),
        patch(
            "sentinel_backend.services.anomaly_engine.publish_event",
            new_callable=AsyncMock,
        ) as mock_alert_pub,
    ):
        await evaluate_run_anomalies(alert_db, "run_pub_1")
        alert_calls = [c for c in mock_alert_pub.call_args_list if c.args[1] == "ALERT_CREATED"]
        assert len(alert_calls) == 2
        assert all(c.args[2]["team"] == "fraud-detection" for c in alert_calls)

    # APPROVAL_REQUIRED payload includes team
    appr_db = AsyncMock()
    appr_db.add = MagicMock()
    span_mock = MagicMock()
    span_mock.run_id = "run_pub_1"
    appr_db.get.side_effect = [run, span_mock]
    appr_db.execute.return_value = empty_res
    with patch(
        "sentinel_backend.services.governance.publish_event",
        new_callable=AsyncMock,
    ) as mock_gov_pub:
        await create_approval_request(
            appr_db,
            ApprovalRequestCreate(
                run_id="run_pub_1",
                span_id="span_pub_1",
                agent_id="fraud-agent",
                tool_name="charge_card",
                sanitized_args={},
                risk_level="HIGH",
                policy_reason="Approval needed",
            ),
        )
        appr_calls = [c for c in mock_gov_pub.call_args_list if c.args[1] == "APPROVAL_REQUIRED"]
        assert len(appr_calls) == 2
        assert all(c.args[2]["team"] == "fraud-detection" for c in appr_calls)


def test_websocket_token_and_team_filtering():
    fraud_actor = ActorContext(
        actor_id="fraud@acme.io",
        actor_role="operator",
        allowed_teams=["fraud-detection"],
        is_demo=False,
    )
    fraud_token = _make_jwt(fraud_actor)

    async def fake_subscribe(_channel: str):
        yield {"type": "FLEET_UPDATED", "data": {"team": "it-ops", "run_ids": ["r_ops"]}}
        yield {"type": "FLEET_UPDATED", "data": {"team": "demo-sandbox", "run_ids": ["r_demo"]}}
        yield {"type": "RUN_UPDATED", "data": {"team": "fraud-detection", "run_id": "r_fraud"}}
        yield {"type": "ALERT_CREATED", "data": {"team": "fraud-detection", "alert_id": "a_fraud"}}

    client = TestClient(app)

    # Invalid JWT closes with 1008
    with (
        pytest.raises(Exception),  # noqa: B017
        client.websocket_connect("/ws/fleet?token=invalid-token") as ws,
    ):
        ws.receive_json()

    # Valid fraud-detection JWT receives ONLY fraud-detection events
    with (
        patch("sentinel_backend.api.ws.subscribe_channel", side_effect=fake_subscribe),
        client.websocket_connect(f"/ws/fleet?token={fraud_token}") as ws,
    ):
        msg1 = ws.receive_json()
        msg2 = ws.receive_json()
        assert msg1["data"]["team"] == "fraud-detection"
        assert msg1["type"] == "RUN_UPDATED"
        assert msg2["data"]["team"] == "fraud-detection"
        assert msg2["type"] == "ALERT_CREATED"

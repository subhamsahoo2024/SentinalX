from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import jwt
import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from sentinel_backend.config import settings
from sentinel_backend.db.session import get_db
from sentinel_backend.main import app
from sentinel_backend.models.audit import AuditEvent
from sentinel_backend.models.policy import Policy
from sentinel_backend.models.run import Run
from sentinel_backend.models.span import Span
from sentinel_backend.schemas.policies import (
    PolicyCreate,
    PolicyDTO,
    PolicyUpdate,
)
from sentinel_backend.services.anomaly_engine import evaluate_run_anomalies
from sentinel_backend.services.policy_service import (
    resolve_effective_policy,
    seed_default_policy,
)
from sqlalchemy.ext.asyncio import AsyncSession


# ==============================================================================
# Model Tests
# ==============================================================================
def test_policy_model_instantiation():
    now = datetime.now(UTC)
    p = Policy(
        policy_id="pol_test_1",
        name="Test Policy",
        team="security",
        agent_id="audit_agent",
        max_tokens=8000,
        max_cost_usd=Decimal("1.2500"),
        loop_threshold=5,
        loop_window_sec=45,
        auto_block_on_budget=True,
        protected_tools=["delete_database", "restart_production_cluster"],
        enabled=True,
        updated_at=now,
    )
    assert p.policy_id == "pol_test_1"
    assert p.name == "Test Policy"
    assert p.team == "security"
    assert p.agent_id == "audit_agent"
    assert p.max_tokens == 8000
    assert p.max_cost_usd == Decimal("1.2500")
    assert p.loop_threshold == 5
    assert p.loop_window_sec == 45
    assert p.auto_block_on_budget is True
    assert p.protected_tools == ["delete_database", "restart_production_cluster"]
    assert p.enabled is True
    assert p.updated_at == now


# ==============================================================================
# Schema Tests
# ==============================================================================
def test_policy_create_defaults():
    pc = PolicyCreate(name="Default Schema Policy")
    assert pc.name == "Default Schema Policy"
    assert pc.team is None
    assert pc.agent_id is None
    assert pc.max_tokens == 5000
    assert pc.max_cost_usd == 0.50
    assert pc.loop_threshold == 3
    assert pc.loop_window_sec == 30
    assert pc.auto_block_on_budget is False
    assert pc.protected_tools == []
    assert pc.enabled is True


def test_policy_create_forbids_extra_fields():
    with pytest.raises(ValidationError):
        PolicyCreate(name="Bad Policy", extra_unknown_field="invalid")


def test_policy_update_all_optional():
    pu = PolicyUpdate()
    assert pu.name is None
    assert pu.team is None
    assert pu.agent_id is None
    assert pu.max_tokens is None
    assert pu.max_cost_usd is None
    assert pu.loop_threshold is None
    assert pu.loop_window_sec is None
    assert pu.auto_block_on_budget is None
    assert pu.protected_tools is None
    assert pu.enabled is None

    pu2 = PolicyUpdate(max_tokens=10000, auto_block_on_budget=True)
    assert pu2.max_tokens == 10000
    assert pu2.auto_block_on_budget is True


def test_policy_dto_from_attributes():
    now = datetime.now(UTC)
    model = Policy(
        policy_id="pol_dto_test",
        name="DTO Policy",
        team="platform",
        agent_id=None,
        max_tokens=6000,
        max_cost_usd=Decimal("0.7500"),
        loop_threshold=4,
        loop_window_sec=20,
        auto_block_on_budget=True,
        protected_tools=["shutdown_vm"],
        enabled=True,
        updated_at=now,
    )
    dto = PolicyDTO.model_validate(model)
    assert dto.policy_id == "pol_dto_test"
    assert dto.name == "DTO Policy"
    assert dto.team == "platform"
    assert dto.agent_id is None
    assert dto.max_tokens == 6000
    assert dto.max_cost_usd == 0.75
    assert dto.loop_threshold == 4
    assert dto.loop_window_sec == 20
    assert dto.auto_block_on_budget is True
    assert dto.protected_tools == ["shutdown_vm"]
    assert dto.enabled is True
    assert dto.updated_at == now


# ==============================================================================
# Service Tests: seed_default_policy
# ==============================================================================
@pytest.mark.asyncio
async def test_seed_default_policy_when_empty():
    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    mock_count_res = MagicMock()
    mock_count_res.scalar_one.return_value = 0
    mock_db.execute.return_value = mock_count_res

    await seed_default_policy(mock_db)

    assert mock_db.add.called
    added_policy = mock_db.add.call_args[0][0]
    assert added_policy.policy_id == "pol_default"
    assert added_policy.name == "Global Default Governance Policy"
    assert added_policy.team is None
    assert added_policy.agent_id is None
    assert added_policy.max_tokens == 5000
    assert added_policy.max_cost_usd == Decimal("0.5000")
    assert added_policy.loop_threshold == 3
    assert added_policy.loop_window_sec == 30
    assert added_policy.auto_block_on_budget is False
    assert added_policy.protected_tools == ["restart_production_cluster"]
    assert added_policy.enabled is True
    assert mock_db.commit.called


@pytest.mark.asyncio
async def test_seed_default_policy_when_not_empty():
    mock_db = AsyncMock()
    mock_count_res = MagicMock()
    mock_count_res.scalar_one.return_value = 1
    mock_db.execute.return_value = mock_count_res

    await seed_default_policy(mock_db)

    assert not mock_db.add.called
    assert not mock_db.commit.called


# ==============================================================================
# Service Tests: resolve_effective_policy
# ==============================================================================
@pytest.mark.asyncio
async def test_resolve_effective_policy_priority_agent():
    mock_db = AsyncMock()
    now = datetime.now(UTC)

    pol_global = Policy(
        policy_id="pol_default",
        name="Global",
        team=None,
        agent_id=None,
        max_tokens=5000,
        max_cost_usd=Decimal("0.5000"),
        loop_threshold=3,
        loop_window_sec=30,
        auto_block_on_budget=False,
        protected_tools=[],
        enabled=True,
        updated_at=now,
    )
    pol_team = Policy(
        policy_id="pol_secops",
        name="SecOps Team",
        team="secops",
        agent_id=None,
        max_tokens=8000,
        max_cost_usd=Decimal("1.0000"),
        loop_threshold=4,
        loop_window_sec=30,
        auto_block_on_budget=False,
        protected_tools=[],
        enabled=True,
        updated_at=now,
    )
    pol_agent = Policy(
        policy_id="pol_bot",
        name="Bot Specific",
        team=None,
        agent_id="bot_1",
        max_tokens=15000,
        max_cost_usd=Decimal("2.5000"),
        loop_threshold=6,
        loop_window_sec=60,
        auto_block_on_budget=True,
        protected_tools=["restart_production_cluster"],
        enabled=True,
        updated_at=now,
    )

    mock_res = MagicMock()
    mock_res.scalars.return_value.all.return_value = [pol_global, pol_team, pol_agent]
    mock_db.execute.return_value = mock_res

    resolved = await resolve_effective_policy(mock_db, team="secops", agent_id="bot_1")
    assert resolved.policy_id == "pol_bot"
    assert resolved.max_tokens == 15000


@pytest.mark.asyncio
async def test_resolve_effective_policy_priority_team():
    mock_db = AsyncMock()
    now = datetime.now(UTC)

    pol_global = Policy(
        policy_id="pol_default",
        name="Global",
        team=None,
        agent_id=None,
        max_tokens=5000,
        max_cost_usd=Decimal("0.5000"),
        loop_threshold=3,
        loop_window_sec=30,
        auto_block_on_budget=False,
        protected_tools=[],
        enabled=True,
        updated_at=now,
    )
    pol_team = Policy(
        policy_id="pol_secops",
        name="SecOps Team",
        team="secops",
        agent_id=None,
        max_tokens=8000,
        max_cost_usd=Decimal("1.0000"),
        loop_threshold=4,
        loop_window_sec=30,
        auto_block_on_budget=False,
        protected_tools=[],
        enabled=True,
        updated_at=now,
    )

    mock_res = MagicMock()
    mock_res.scalars.return_value.all.return_value = [pol_global, pol_team]
    mock_db.execute.return_value = mock_res

    resolved = await resolve_effective_policy(mock_db, team="secops", agent_id="unknown_agent")
    assert resolved.policy_id == "pol_secops"
    assert resolved.max_tokens == 8000

    resolved_none_agent = await resolve_effective_policy(mock_db, team="secops", agent_id=None)
    assert resolved_none_agent.policy_id == "pol_secops"


@pytest.mark.asyncio
async def test_resolve_effective_policy_priority_global():
    mock_db = AsyncMock()
    now = datetime.now(UTC)

    pol_global = Policy(
        policy_id="pol_default",
        name="Global",
        team=None,
        agent_id=None,
        max_tokens=5000,
        max_cost_usd=Decimal("0.5000"),
        loop_threshold=3,
        loop_window_sec=30,
        auto_block_on_budget=False,
        protected_tools=["restart_production_cluster"],
        enabled=True,
        updated_at=now,
    )

    mock_res = MagicMock()
    mock_res.scalars.return_value.all.return_value = [pol_global]
    mock_db.execute.return_value = mock_res

    resolved = await resolve_effective_policy(mock_db, team="finance", agent_id="finance_bot")
    assert resolved.policy_id == "pol_default"
    assert resolved.max_tokens == 5000


@pytest.mark.asyncio
async def test_resolve_effective_policy_fallback_synthetic():
    mock_db = AsyncMock()
    mock_res = MagicMock()
    mock_res.scalars.return_value.all.return_value = []
    mock_db.execute.return_value = mock_res

    resolved = await resolve_effective_policy(mock_db, team="finance", agent_id="bot_x")
    assert resolved.policy_id == "pol_default"
    assert resolved.name == "Global Default Governance Policy"
    assert resolved.team is None
    assert resolved.agent_id is None
    assert resolved.max_tokens == 5000
    assert resolved.max_cost_usd == Decimal("0.5000")
    assert resolved.protected_tools == ["restart_production_cluster"]
    assert resolved.enabled is True


# ==============================================================================
# API Tests: /api/policies
# ==============================================================================
@pytest.mark.asyncio
async def test_api_list_policies():
    mock_db = AsyncMock(spec=AsyncSession)
    now = datetime.now(UTC)
    pol1 = Policy(
        policy_id="pol_1",
        name="P1",
        team="sec",
        agent_id=None,
        max_tokens=4000,
        max_cost_usd=Decimal("0.4000"),
        loop_threshold=3,
        loop_window_sec=30,
        auto_block_on_budget=False,
        protected_tools=[],
        enabled=True,
        updated_at=now,
    )
    mock_res = MagicMock()
    mock_res.scalars.return_value.all.return_value = [pol1]
    mock_db.execute.return_value = mock_res

    app.dependency_overrides[get_db] = lambda: mock_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/policies")
            assert resp.status_code == 200
            data = resp.json()
            assert len(data) == 1
            assert data[0]["policy_id"] == "pol_1"
            assert data[0]["max_tokens"] == 4000
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.mark.asyncio
async def test_api_create_policy_rbac_and_audit():
    mock_db = AsyncMock(spec=AsyncSession)
    mock_db.add = MagicMock()
    mock_db.commit = AsyncMock()
    mock_db.refresh = AsyncMock()
    exec_res = MagicMock()
    exec_res.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = exec_res

    app.dependency_overrides[get_db] = lambda: mock_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # 1. Viewer role rejected with 403 Forbidden
            resp_viewer = await client.post(
                "/api/policies",
                headers={"X-Actor-Id": "u_viewer", "X-Actor-Role": "viewer"},
                json={"name": "Viewer Policy"},
            )
            assert resp_viewer.status_code == 403

            # 2. Approver role succeeds
            payload = {
                "name": "SecOps Strict Policy",
                "team": "secops",
                "max_tokens": 12000,
                "max_cost_usd": 1.50,
                "loop_threshold": 4,
                "loop_window_sec": 40,
                "auto_block_on_budget": True,
                "protected_tools": ["wipe_db"],
                "enabled": True,
            }
            resp_approver = await client.post(
                "/api/policies",
                headers={"X-Actor-Id": "admin-1", "X-Actor-Role": "approver"},
                json=payload,
            )
            assert resp_approver.status_code == 200
            data = resp_approver.json()
            assert data["name"] == "SecOps Strict Policy"
            assert data["max_tokens"] == 12000
            assert data["max_cost_usd"] == 1.50
            assert data["auto_block_on_budget"] is True
            assert data["policy_id"].startswith("pol_")

            # Verify AuditEvent added
            added = [call.args[0] for call in mock_db.add.call_args_list]
            audits = [x for x in added if isinstance(x, AuditEvent)]
            assert len(audits) == 1
            assert audits[0].action == "POLICY_CREATED"
            assert audits[0].actor_id == "admin-1"
            assert audits[0].target_type == "policy"
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.mark.asyncio
async def test_api_update_policy():
    mock_db = AsyncMock(spec=AsyncSession)
    now = datetime.now(UTC)
    existing_policy = Policy(
        policy_id="pol_update_me",
        name="Old Policy",
        team="dev",
        agent_id=None,
        max_tokens=3000,
        max_cost_usd=Decimal("0.3000"),
        loop_threshold=3,
        loop_window_sec=30,
        auto_block_on_budget=False,
        protected_tools=[],
        enabled=True,
        updated_at=now,
    )

    async def mock_get(entity, ident):
        if entity == Policy and ident == "pol_update_me":
            return existing_policy
        return None

    mock_db.get.side_effect = mock_get
    mock_db.add = MagicMock()
    mock_db.commit = AsyncMock()
    mock_db.refresh = AsyncMock()
    exec_res = MagicMock()
    exec_res.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = exec_res

    app.dependency_overrides[get_db] = lambda: mock_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # 404 for missing policy
            resp_404 = await client.patch(
                "/api/policies/pol_missing",
                headers={"X-Actor-Id": "admin-1", "X-Actor-Role": "approver"},
                json={"name": "New Name"},
            )
            assert resp_404.status_code == 404

            # 403 for viewer
            resp_403 = await client.patch(
                "/api/policies/pol_update_me",
                headers={"X-Actor-Id": "u_viewer", "X-Actor-Role": "viewer"},
                json={"name": "Hacked"},
            )
            assert resp_403.status_code == 403

            # Success with approver
            resp_ok = await client.patch(
                "/api/policies/pol_update_me",
                headers={"X-Actor-Id": "lead-sec", "X-Actor-Role": "admin"},
                json={"max_tokens": 7000, "auto_block_on_budget": True},
            )
            assert resp_ok.status_code == 200
            data = resp_ok.json()
            assert data["max_tokens"] == 7000
            assert data["auto_block_on_budget"] is True

            # Verify AuditEvent added
            added = [call.args[0] for call in mock_db.add.call_args_list]
            audits = [x for x in added if isinstance(x, AuditEvent)]
            assert len(audits) == 1
            assert audits[0].action == "POLICY_UPDATED"
            assert audits[0].actor_id == "lead-sec"
    finally:
        app.dependency_overrides.pop(get_db, None)


# ==============================================================================
# API Tests: /api/runs/{run_id}/cancel and control-state
# ==============================================================================
@pytest.mark.asyncio
async def test_api_cancel_run():
    mock_db = AsyncMock(spec=AsyncSession)
    now = datetime.now(UTC)
    active_run = Run(
        run_id="run_cancel_target",
        trace_id="t" * 32,
        team="secops",
        status="RUNNING",
        started_at=now - timedelta(minutes=5),
        last_event_at=now,
        total_tokens=1500,
        total_cost_usd=Decimal("0.1200"),
    )
    succeeded_run = Run(
        run_id="run_already_terminal",
        trace_id="s" * 32,
        team="secops",
        status="SUCCEEDED",
        started_at=now - timedelta(minutes=10),
        ended_at=now - timedelta(minutes=5),
        last_event_at=now,
    )

    async def mock_get(entity, ident):
        if entity == Run and ident == "run_cancel_target":
            return active_run
        if entity == Run and ident == "run_already_terminal":
            return succeeded_run
        return None

    mock_db.get.side_effect = mock_get
    mock_db.add = MagicMock()
    mock_db.commit = AsyncMock()
    mock_db.refresh = AsyncMock()
    exec_res = MagicMock()
    exec_res.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = exec_res

    spans_mock = MagicMock()
    spans_mock.one.return_value = (5, 0)
    mock_db.execute.return_value = spans_mock

    app.dependency_overrides[get_db] = lambda: mock_db

    def _org_headers(actor_id: str, role: str) -> dict[str, str]:
        token = jwt.encode(
            {
                "sub": actor_id,
                "email": actor_id,
                "name": actor_id,
                "role": role,
                "allowed_teams": ["secops"],
                "is_demo": False,
                "exp": datetime.now(UTC) + timedelta(minutes=30),
            },
            settings.JWT_SECRET,
            algorithm="HS256",
        )
        return {"Authorization": f"Bearer {token}"}

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # 1. 403 Forbidden for viewer
            resp_viewer = await client.post(
                "/api/runs/run_cancel_target/cancel",
                headers=_org_headers("v1", "viewer"),
            )
            assert resp_viewer.status_code == 403

            # 2. 404 for missing run
            resp_404 = await client.post(
                "/api/runs/run_nonexistent/cancel",
                headers=_org_headers("admin-1", "approver"),
            )
            assert resp_404.status_code == 404

            # 3. 409 Conflict for already terminal run
            resp_409 = await client.post(
                "/api/runs/run_already_terminal/cancel",
                headers=_org_headers("admin-1", "approver"),
            )
            assert resp_409.status_code == 409

            # 4. Successful cancellation
            mock_redis = AsyncMock()
            with (
                patch("sentinel_backend.api.runs.get_redis_client", return_value=mock_redis),
                patch("sentinel_backend.api.runs.publish_event", new_callable=AsyncMock) as mock_pub,
            ):
                resp_cancel = await client.post(
                    "/api/runs/run_cancel_target/cancel",
                    headers=_org_headers("operator-1", "approver"),
                )
                assert resp_cancel.status_code == 200
                data = resp_cancel.json()
                assert data["status"] == "CANCELLED"
                assert active_run.status == "CANCELLED"

                # Verify Redis key set
                mock_redis.set.assert_called_once_with(
                    "run:run_cancel_target:cancelled", "1", ex=3600
                )

                # Verify AuditEvent recorded
                added = [call.args[0] for call in mock_db.add.call_args_list]
                audits = [x for x in added if isinstance(x, AuditEvent)]
                assert len(audits) == 1
                assert audits[0].action == "RUN_CANCELLED"
                assert audits[0].target_id == "run_cancel_target"

                # Verify broadcast events
                assert mock_pub.call_count == 2
                channels = [c.args[0] for c in mock_pub.call_args_list]
                assert "run:run_cancel_target:stream" in channels
                assert "fleet:stream" in channels
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.mark.asyncio
async def test_api_run_control_state():
    mock_redis = AsyncMock()

    async def mock_redis_get(key: str):
        if "cancelled" in key:
            return "1"
        if "blocked" in key:
            return "BUDGET_EXCEEDED"
        return None

    mock_redis.get.side_effect = mock_redis_get

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. 401 Unauthorized without API key
        resp_no_auth = await client.get("/api/runs/run_123/control-state")
        assert resp_no_auth.status_code == 401

        # 2. 200 OK with valid API key
        with patch("sentinel_backend.api.runs.get_redis_client", return_value=mock_redis):
            resp = await client.get(
                "/api/runs/run_123/control-state",
                headers={"X-API-Key": settings.SENTINEL_API_KEY},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["run_id"] == "run_123"
            assert data["cancelled"] is True
            assert data["blocked_reason"] == "BUDGET_EXCEEDED"


# ==============================================================================
# Anomaly Engine: Dynamic Policy & Circuit Breaking Tests
# ==============================================================================
@pytest.mark.asyncio
async def test_evaluate_run_anomalies_dynamic_policy_and_auto_block():
    now = datetime.now(UTC)
    run = Run(
        run_id="run_circuit_breaker",
        trace_id="c" * 32,
        team="secops",
        root_agent_id="bot_sec",
        status="RUNNING",
        started_at=now - timedelta(seconds=20),
        last_event_at=now,
        total_tokens=2000,
        total_cost_usd=Decimal("0.8500"),  # > custom policy max_cost_usd (0.50)
    )

    span1 = Span(
        span_id="s_llm_cost",
        trace_id="c" * 32,
        run_id="run_circuit_breaker",
        agent_id="bot_sec",
        span_type="LLM",
        operation_name="gpt-4o",
        status="SUCCEEDED",
        started_at=now - timedelta(seconds=15),
        direct_cost_usd=Decimal("0.8500"),
        input_tokens=1500,
        output_tokens=500,
    )

    custom_policy = Policy(
        policy_id="pol_sec_strict",
        name="Strict Policy",
        team="secops",
        agent_id="bot_sec",
        max_tokens=10000,
        max_cost_usd=Decimal("0.5000"),
        loop_threshold=2,
        loop_window_sec=15,
        auto_block_on_budget=True,
        protected_tools=[],
        enabled=True,
        updated_at=now,
    )

    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    mock_db.commit = AsyncMock()
    mock_db.get.return_value = run

    def execute_side_effect(stmt):
        s_stmt = str(stmt).lower()
        if "from policies" in s_stmt:
            res = MagicMock()
            res.scalars.return_value.all.return_value = [custom_policy]
            return res
        if "from spans" in s_stmt:
            res = MagicMock()
            res.scalars.return_value.all.return_value = [span1]
            return res
        # alert query
        res = MagicMock()
        res.scalar_one_or_none.return_value = None
        return res

    mock_db.execute.side_effect = execute_side_effect
    mock_redis = AsyncMock()

    with (
        patch("sentinel_backend.services.anomaly_engine.publish_event", new_callable=AsyncMock),
        patch("sentinel_backend.services.anomaly_engine.get_redis_client", return_value=mock_redis),
    ):
        alerts = await evaluate_run_anomalies(mock_db, "run_circuit_breaker")
        assert len(alerts) == 1
        alert = alerts[0]
        assert alert.rule_id == "BUDGET_EXCEEDED"
        assert alert.evidence["cost_exceeded"] is True
        assert alert.evidence["token_exceeded"] is False
        assert alert.evidence["auto_block_on_budget"] is True

        # Verify circuit breaking Redis key set
        mock_redis.set.assert_called_once_with(
            "run:run_circuit_breaker:blocked", "BUDGET_EXCEEDED", ex=3600
        )

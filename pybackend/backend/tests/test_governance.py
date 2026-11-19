import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
from sentinel_backend.api.deps import (
    ActorContext,
    get_current_actor,
    require_approver,
)
from sentinel_backend.config import settings
from sentinel_backend.db.session import get_db
from sentinel_backend.main import app
from sentinel_backend.models.approval import Approval
from sentinel_backend.models.audit import AuditEvent
from sentinel_backend.models.run import Run
from sentinel_backend.models.span import Span
from sentinel_backend.schemas.governance import (
    ApprovalDecisionRequest,
    ApprovalDTO,
    ApprovalRequestCreate,
    AuditEventDTO,
)
from sentinel_backend.services.governance import (
    create_approval_request,
    decide_approval,
    wait_for_approval_decision,
)
from sqlalchemy.ext.asyncio import AsyncSession


# ==============================================================================
# Unit Tests: Schemas
# ==============================================================================
def test_approval_request_create_schema():
    req = ApprovalRequestCreate(
        run_id="run_123",
        span_id="span_456",
        agent_id="remediation-agent",
        tool_name="restart_service",
        sanitized_args={"service": "auth_db"},
        risk_level="HIGH",
        policy_reason="Service restart requires operator signoff",
    )
    assert req.run_id == "run_123"
    assert req.risk_level == "HIGH"
    assert req.sanitized_args == {"service": "auth_db"}


def test_approval_decision_request_schema():
    req = ApprovalDecisionRequest(decision="APPROVED", comment="Looks safe to restart")
    assert req.decision == "APPROVED"
    assert req.comment == "Looks safe to restart"

    req_reject = ApprovalDecisionRequest(decision="REJECTED")
    assert req_reject.decision == "REJECTED"
    assert req_reject.comment is None


def test_approval_dto_model_validate():
    now = datetime.now(UTC)
    approval = Approval(
        approval_id="apr_abcdef123456",
        run_id="run_123",
        span_id="span_456",
        agent_id="remediation-agent",
        tool_name="restart_service",
        sanitized_args={"cluster": "prod"},
        risk_level="CRITICAL",
        policy_reason="Production modification",
        status="PENDING",
        decided_by=None,
        decided_at=None,
        comment=None,
        created_at=now,
    )
    dto = ApprovalDTO.model_validate(approval)
    assert dto.approval_id == "apr_abcdef123456"
    assert dto.status == "PENDING"
    assert dto.created_at == now


def test_audit_event_dto_model_validate():
    now = datetime.now(UTC)
    audit = AuditEvent(
        audit_id="audit_abcdef123456",
        actor_id="admin-user",
        actor_role="admin",
        action="APPROVAL_APPROVED",
        target_type="approval",
        target_id="apr_abcdef123456",
        payload={"run_id": "run_123", "comment": "approved"},
        created_at=now,
    )
    dto = AuditEventDTO.model_validate(audit)
    assert dto.audit_id == "audit_abcdef123456"
    assert dto.action == "APPROVAL_APPROVED"


# ==============================================================================
# Unit Tests: RBAC Dependencies
# ==============================================================================
@pytest.mark.asyncio
async def test_get_current_actor_valid_roles():
    for role in ["viewer", "operator", "approver", "admin"]:
        actor = await get_current_actor(x_actor_id=f"user-{role}", x_actor_role=role)
        assert actor.actor_id == f"user-{role}"
        assert actor.actor_role == role


@pytest.mark.asyncio
async def test_get_current_actor_invalid_role():
    with pytest.raises(HTTPException) as exc_info:
        await get_current_actor(x_actor_id="user-bad", x_actor_role="superadmin")
    assert exc_info.value.status_code == 400
    assert "Invalid actor role" in exc_info.value.detail


@pytest.mark.asyncio
async def test_require_approver_success():
    actor_approver = ActorContext(actor_id="alice", actor_role="approver")
    res1 = await require_approver(actor_approver)
    assert res1.actor_id == "alice"

    actor_admin = ActorContext(actor_id="bob", actor_role="admin")
    res2 = await require_approver(actor_admin)
    assert res2.actor_id == "bob"


@pytest.mark.asyncio
async def test_require_approver_forbidden():
    actor_viewer = ActorContext(actor_id="charlie", actor_role="viewer")
    with pytest.raises(HTTPException) as exc_info:
        await require_approver(actor_viewer)
    assert exc_info.value.status_code == 403

    actor_operator = ActorContext(actor_id="david", actor_role="operator")
    with pytest.raises(HTTPException) as exc_info2:
        await require_approver(actor_operator)
    assert exc_info2.value.status_code == 403


# ==============================================================================
# Unit Tests: Governance Services
# ==============================================================================
@pytest.mark.asyncio
async def test_create_approval_request_service():
    mock_db = AsyncMock(spec=AsyncSession)
    mock_span = Span(span_id="span_101", run_id="run_202", status="RUNNING")
    mock_run = Run(run_id="run_202", status="RUNNING")

    async def mock_get(entity, ident):
        if entity == Span and ident == "span_101":
            return mock_span
        if entity == Run and ident == "run_202":
            return mock_run
        return None

    mock_db.get.side_effect = mock_get
    exec_result = MagicMock()
    exec_result.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = exec_result

    req = ApprovalRequestCreate(
        run_id="run_202",
        span_id="span_101",
        agent_id="remediation-agent",
        tool_name="drop_partition",
        sanitized_args={"table": "events"},
        risk_level="HIGH",
        policy_reason="Destructive DDL",
    )

    with patch("sentinel_backend.services.governance.publish_event", new_callable=AsyncMock) as mock_pub:
        dto = await create_approval_request(mock_db, req)

        assert dto.approval_id.startswith("apr_")
        assert len(dto.approval_id) == 16  # "apr_" + 12 chars
        assert dto.status == "PENDING"
        assert mock_span.status == "AWAITING_APPROVAL"
        assert mock_run.status == "AWAITING_APPROVAL"
        assert mock_db.commit.called
        assert mock_pub.call_count == 2
        # Check published channels
        called_channels = [call.args[0] for call in mock_pub.call_args_list]
        assert "fleet:stream" in called_channels
        assert "run:run_202:stream" in called_channels


@pytest.mark.asyncio
async def test_create_approval_request_missing_run():
    mock_db = AsyncMock(spec=AsyncSession)
    mock_db.get.return_value = None

    req = ApprovalRequestCreate(
        run_id="run_missing",
        span_id="span_101",
        agent_id="agent_1",
        tool_name="test_tool",
        sanitized_args={},
        risk_level="HIGH",
        policy_reason="test",
    )

    with pytest.raises(HTTPException) as exc_info:
        await create_approval_request(mock_db, req)
    assert exc_info.value.status_code == 404
    assert "Run 'run_missing' not found" in exc_info.value.detail


@pytest.mark.asyncio
async def test_create_approval_request_missing_span():
    mock_db = AsyncMock(spec=AsyncSession)
    mock_run = Run(run_id="run_exists", status="RUNNING")

    async def mock_get(entity, ident):
        if entity == Run and ident == "run_exists":
            return mock_run
        return None

    mock_db.get.side_effect = mock_get

    req = ApprovalRequestCreate(
        run_id="run_exists",
        span_id="span_missing",
        agent_id="agent_1",
        tool_name="test_tool",
        sanitized_args={},
        risk_level="HIGH",
        policy_reason="test",
    )

    with pytest.raises(HTTPException) as exc_info:
        await create_approval_request(mock_db, req)
    assert exc_info.value.status_code == 404
    assert "Span 'span_missing' not found" in exc_info.value.detail


@pytest.mark.asyncio
async def test_create_approval_request_span_run_mismatch():
    mock_db = AsyncMock(spec=AsyncSession)
    mock_run = Run(run_id="run_1", status="RUNNING")
    mock_span = Span(span_id="span_1", run_id="run_OTHER", status="RUNNING")

    async def mock_get(entity, ident):
        if entity == Run and ident == "run_1":
            return mock_run
        if entity == Span and ident == "span_1":
            return mock_span
        return None

    mock_db.get.side_effect = mock_get

    req = ApprovalRequestCreate(
        run_id="run_1",
        span_id="span_1",
        agent_id="agent_1",
        tool_name="test_tool",
        sanitized_args={},
        risk_level="HIGH",
        policy_reason="test",
    )

    with pytest.raises(HTTPException) as exc_info:
        await create_approval_request(mock_db, req)
    assert exc_info.value.status_code == 400
    assert "does not belong to run" in exc_info.value.detail


@pytest.mark.asyncio
async def test_create_approval_request_already_exists():
    mock_db = AsyncMock(spec=AsyncSession)
    mock_run = Run(run_id="run_1", status="RUNNING")
    mock_span = Span(span_id="span_1", run_id="run_1", status="RUNNING")
    mock_existing_approval = Approval(
        approval_id="apr_already",
        run_id="run_1",
        span_id="span_1",
        agent_id="agent_1",
        tool_name="tool_1",
        sanitized_args={},
        risk_level="HIGH",
        policy_reason="test",
        status="PENDING",
        created_at=datetime.now(UTC),
    )

    async def mock_get(entity, ident):
        if entity == Run and ident == "run_1":
            return mock_run
        if entity == Span and ident == "span_1":
            return mock_span
        return None

    mock_db.get.side_effect = mock_get
    exec_result = MagicMock()
    exec_result.scalar_one_or_none.return_value = mock_existing_approval
    mock_db.execute.return_value = exec_result

    req = ApprovalRequestCreate(
        run_id="run_1",
        span_id="span_1",
        agent_id="agent_1",
        tool_name="test_tool",
        sanitized_args={},
        risk_level="HIGH",
        policy_reason="test",
    )

    with pytest.raises(HTTPException) as exc_info:
        await create_approval_request(mock_db, req)
    assert exc_info.value.status_code == 409
    assert "already exists" in exc_info.value.detail


@pytest.mark.asyncio
async def test_wait_for_approval_decision_immediate():
    mock_db = AsyncMock(spec=AsyncSession)
    mock_approval = Approval(
        approval_id="apr_123456789012",
        run_id="run_1",
        span_id="span_1",
        agent_id="agent_1",
        tool_name="test_tool",
        sanitized_args={},
        risk_level="HIGH",
        policy_reason="policy",
        status="APPROVED",
        decided_by="admin-1",
        decided_at=datetime.now(UTC),
        comment="looks good",
        created_at=datetime.now(UTC),
    )
    mock_db.get.return_value = mock_approval

    res = await wait_for_approval_decision(mock_db, "apr_123456789012", timeout_sec=2)
    assert res["status"] == "APPROVED"
    assert res["decided_by"] == "admin-1"
    assert res["comment"] == "looks good"


@pytest.mark.asyncio
async def test_wait_for_approval_decision_not_found():
    mock_db = AsyncMock(spec=AsyncSession)
    mock_db.get.return_value = None

    with pytest.raises(HTTPException) as exc_info:
        await wait_for_approval_decision(mock_db, "apr_missing")
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_wait_for_approval_decision_pubsub():
    mock_db = AsyncMock(spec=AsyncSession)
    mock_approval = Approval(
        approval_id="apr_pending123",
        run_id="run_1",
        span_id="span_1",
        agent_id="agent_1",
        tool_name="test_tool",
        sanitized_args={},
        risk_level="HIGH",
        policy_reason="policy",
        status="PENDING",
        decided_by=None,
        decided_at=None,
        comment=None,
        created_at=datetime.now(UTC),
    )
    mock_db.get.return_value = mock_approval

    async def mock_stream(_):
        await asyncio.sleep(0.01)
        yield {
            "type": "APPROVAL_DECIDED",
            "data": {
                "approval_id": "apr_pending123",
                "status": "APPROVED",
                "decided_by": "approver-1",
                "comment": "all clear",
            },
        }

    with patch("sentinel_backend.services.governance.subscribe_channel", side_effect=mock_stream):
        res = await wait_for_approval_decision(mock_db, "apr_pending123", timeout_sec=2)
        assert res["status"] == "APPROVED"
        assert res["decided_by"] == "approver-1"


@pytest.mark.asyncio
async def test_wait_for_approval_decision_timeout():
    mock_db = AsyncMock(spec=AsyncSession)
    mock_approval = Approval(
        approval_id="apr_timeout123",
        run_id="run_1",
        span_id="span_1",
        agent_id="agent_1",
        tool_name="test_tool",
        sanitized_args={},
        risk_level="HIGH",
        policy_reason="policy",
        status="PENDING",
        decided_by=None,
        decided_at=None,
        comment=None,
        created_at=datetime.now(UTC),
    )
    mock_db.get.return_value = mock_approval

    async def mock_stream_hangs(_):
        await asyncio.sleep(10)
        yield {"data": {}}

    with patch("sentinel_backend.services.governance.subscribe_channel", side_effect=mock_stream_hangs):
        res = await wait_for_approval_decision(mock_db, "apr_timeout123", timeout_sec=0.05)
        assert res["status"] == "PENDING"
        assert res["approval_id"] == "apr_timeout123"


@pytest.mark.asyncio
async def test_decide_approval_approved():
    mock_db = AsyncMock(spec=AsyncSession)
    mock_approval = Approval(
        approval_id="apr_approve_me",
        run_id="run_100",
        span_id="span_200",
        agent_id="db-agent",
        tool_name="truncate",
        sanitized_args={},
        risk_level="HIGH",
        policy_reason="High risk",
        status="PENDING",
        decided_by=None,
        decided_at=None,
        comment=None,
        created_at=datetime.now(UTC),
    )
    mock_span = Span(span_id="span_200", run_id="run_100", status="AWAITING_APPROVAL")
    mock_run = Run(run_id="run_100", status="AWAITING_APPROVAL")

    exec_result = MagicMock()
    exec_result.scalar_one_or_none.return_value = mock_approval
    mock_db.execute.return_value = exec_result

    async def mock_get(entity, ident):
        if entity == Span and ident == "span_200":
            return mock_span
        if entity == Run and ident == "run_100":
            return mock_run
        return None

    mock_db.get.side_effect = mock_get

    actor = ActorContext(actor_id="lead-engineer", actor_role="approver")
    body = ApprovalDecisionRequest(decision="APPROVED", comment="Authorized per ticket #884")

    with patch("sentinel_backend.services.governance.publish_event", new_callable=AsyncMock) as mock_pub:
        dto = await decide_approval(mock_db, "apr_approve_me", body, actor)

        assert dto.status == "APPROVED"
        assert dto.decided_by == "lead-engineer"
        assert dto.comment == "Authorized per ticket #884"
        assert mock_span.status == "RUNNING"
        assert mock_run.status == "RUNNING"
        assert mock_db.commit.called
        assert mock_db.add.called
        # Verify AuditEvent was added
        added_entities = [call.args[0] for call in mock_db.add.call_args_list]
        audit_events = [e for e in added_entities if isinstance(e, AuditEvent)]
        assert len(audit_events) == 1
        assert audit_events[0].action == "APPROVAL_APPROVED"
        assert audit_events[0].actor_id == "lead-engineer"
        assert audit_events[0].actor_role == "approver"

        # Check published channels
        assert mock_pub.call_count == 3
        channels = [call.args[0] for call in mock_pub.call_args_list]
        assert "approval:apr_approve_me:decision" in channels
        assert "run:run_100:stream" in channels
        assert "fleet:stream" in channels


@pytest.mark.asyncio
async def test_decide_approval_rejected():
    mock_db = AsyncMock(spec=AsyncSession)
    mock_approval = Approval(
        approval_id="apr_reject_me",
        run_id="run_100",
        span_id="span_200",
        agent_id="db-agent",
        tool_name="drop_db",
        sanitized_args={},
        risk_level="CRITICAL",
        policy_reason="Policy block",
        status="PENDING",
        decided_by=None,
        decided_at=None,
        comment=None,
        created_at=datetime.now(UTC),
    )
    mock_span = Span(span_id="span_200", run_id="run_100", status="AWAITING_APPROVAL")
    mock_run = Run(run_id="run_100", status="AWAITING_APPROVAL")

    exec_result = MagicMock()
    exec_result.scalar_one_or_none.return_value = mock_approval
    mock_db.execute.return_value = exec_result

    async def mock_get(entity, ident):
        if entity == Span and ident == "span_200":
            return mock_span
        if entity == Run and ident == "run_100":
            return mock_run
        return None

    mock_db.get.side_effect = mock_get

    actor = ActorContext(actor_id="sec-admin", actor_role="admin")
    body = ApprovalDecisionRequest(decision="REJECTED", comment="Operation unsafe")

    with patch("sentinel_backend.services.governance.publish_event", new_callable=AsyncMock):
        dto = await decide_approval(mock_db, "apr_reject_me", body, actor)

        assert dto.status == "REJECTED"
        assert mock_span.status == "CANCELLED"
        assert mock_run.status == "RUNNING"


@pytest.mark.asyncio
async def test_decide_approval_conflict_when_already_decided():
    mock_db = AsyncMock(spec=AsyncSession)
    mock_approval = Approval(
        approval_id="apr_already_done",
        run_id="run_1",
        span_id="span_1",
        agent_id="agent_1",
        tool_name="test",
        sanitized_args={},
        risk_level="HIGH",
        policy_reason="policy",
        status="APPROVED",
        decided_by="someone",
        decided_at=datetime.now(UTC),
        comment=None,
        created_at=datetime.now(UTC),
    )
    exec_result = MagicMock()
    exec_result.scalar_one_or_none.return_value = mock_approval
    mock_db.execute.return_value = exec_result

    actor = ActorContext(actor_id="user1", actor_role="approver")
    body = ApprovalDecisionRequest(decision="REJECTED")

    with pytest.raises(HTTPException) as exc_info:
        await decide_approval(mock_db, "apr_already_done", body, actor)
    assert exc_info.value.status_code == 409


# ==============================================================================
# Integration Tests: Endpoints via AsyncClient
# ==============================================================================
@pytest.mark.asyncio
async def test_api_approvals_request_auth():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Missing API Key -> 401
        res_no_auth = await client.post(
            "/api/approvals/request",
            json={
                "run_id": "r1",
                "span_id": "s1",
                "agent_id": "a1",
                "tool_name": "t1",
                "sanitized_args": {},
                "risk_level": "HIGH",
                "policy_reason": "policy",
            },
        )
        assert res_no_auth.status_code == 401


@pytest.mark.asyncio
async def test_api_approvals_decision_rbac():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Invalid role -> 400
        res_invalid_role = await client.post(
            "/api/approvals/apr_test/decision",
            headers={"X-Actor-Id": "u1", "X-Actor-Role": "unknown-role"},
            json={"decision": "APPROVED"},
        )
        assert res_invalid_role.status_code == 400

        # Viewer role -> 403 Forbidden
        res_viewer = await client.post(
            "/api/approvals/apr_test/decision",
            headers={"X-Actor-Id": "u1", "X-Actor-Role": "viewer"},
            json={"decision": "APPROVED"},
        )
        assert res_viewer.status_code == 403

        # Operator role -> 403 Forbidden
        res_operator = await client.post(
            "/api/approvals/apr_test/decision",
            headers={"X-Actor-Id": "u1", "X-Actor-Role": "operator"},
            json={"decision": "APPROVED"},
        )
        assert res_operator.status_code == 403


@pytest.mark.asyncio
async def test_api_endpoints_end_to_end_flow():
    mock_db = AsyncMock(spec=AsyncSession)

    now = datetime.now(UTC)
    mock_approval = Approval(
        approval_id="apr_flow12345678",
        run_id="run_f1",
        span_id="span_f1",
        agent_id="agent_f1",
        tool_name="restart_gateway",
        sanitized_args={"target": "gw-1"},
        risk_level="HIGH",
        policy_reason="Gateway restart requires approval",
        status="PENDING",
        decided_by=None,
        decided_at=None,
        comment=None,
        created_at=now,
    )
    mock_audit = AuditEvent(
        audit_id="audit_flow123456",
        actor_id="admin-1",
        actor_role="admin",
        action="APPROVAL_APPROVED",
        target_type="approval",
        target_id="apr_flow12345678",
        payload={"comment": "approved"},
        created_at=now,
    )

    app.dependency_overrides[get_db] = lambda: mock_db

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            headers_api_key = {"X-API-Key": settings.SENTINEL_API_KEY}

            # 1. POST /api/approvals/request
            with patch(
                "sentinel_backend.api.approvals.create_approval_request",
                new_callable=AsyncMock,
            ) as mock_create:
                mock_create.return_value = ApprovalDTO.model_validate(mock_approval)
                res_post = await client.post(
                    "/api/approvals/request",
                    headers=headers_api_key,
                    json={
                        "run_id": "run_f1",
                        "span_id": "span_f1",
                        "agent_id": "agent_f1",
                        "tool_name": "restart_gateway",
                        "sanitized_args": {"target": "gw-1"},
                        "risk_level": "HIGH",
                        "policy_reason": "Gateway restart requires approval",
                    },
                )
                assert res_post.status_code == 200
                data = res_post.json()
                assert data["approval_id"] == "apr_flow12345678"
                assert data["status"] == "PENDING"

            # 2. GET /api/approvals/{approval_id}/wait
            with patch(
                "sentinel_backend.api.approvals.wait_for_approval_decision",
                new_callable=AsyncMock,
            ) as mock_wait:
                mock_wait.return_value = {
                    "approval_id": "apr_flow12345678",
                    "status": "APPROVED",
                    "decided_by": "approver-1",
                    "comment": "ok",
                }
                res_wait = await client.get(
                    "/api/approvals/apr_flow12345678/wait?timeout=5",
                    headers=headers_api_key,
                )
                assert res_wait.status_code == 200
                assert res_wait.json()["status"] == "APPROVED"

            # 3. GET /api/approvals (with and without status)
            list_result = MagicMock()
            list_result.scalars.return_value.all.return_value = [mock_approval]
            mock_db.execute.return_value = list_result

            res_list = await client.get("/api/approvals")
            assert res_list.status_code == 200
            assert len(res_list.json()) == 1

            res_list_filter = await client.get("/api/approvals?status=PENDING")
            assert res_list_filter.status_code == 200
            assert len(res_list_filter.json()) == 1

            # 4. POST /api/approvals/{approval_id}/decision with approver role
            decided_approval = Approval(
                approval_id="apr_flow12345678",
                run_id="run_f1",
                span_id="span_f1",
                agent_id="agent_f1",
                tool_name="restart_gateway",
                sanitized_args={"target": "gw-1"},
                risk_level="HIGH",
                policy_reason="Gateway restart requires approval",
                status="APPROVED",
                decided_by="lead-approver",
                decided_at=now,
                comment="authorized",
                created_at=now,
            )
            with patch(
                "sentinel_backend.api.approvals.decide_approval",
                new_callable=AsyncMock,
            ) as mock_decide:
                mock_decide.return_value = ApprovalDTO.model_validate(decided_approval)
                res_decide = await client.post(
                    "/api/approvals/apr_flow12345678/decision",
                    headers={
                        "X-Actor-Id": "lead-approver",
                        "X-Actor-Role": "approver",
                    },
                    json={"decision": "APPROVED", "comment": "authorized"},
                )
                assert res_decide.status_code == 200
                assert res_decide.json()["status"] == "APPROVED"
                assert res_decide.json()["decided_by"] == "lead-approver"

            # 5. GET /api/audit-events
            audit_result = MagicMock()
            audit_result.scalars.return_value.all.return_value = [mock_audit]
            mock_db.execute.return_value = audit_result

            res_audit = await client.get("/api/audit-events")
            assert res_audit.status_code == 200
            assert len(res_audit.json()) == 1
            assert res_audit.json()[0]["audit_id"] == "audit_flow123456"
            assert res_audit.json()[0]["action"] == "APPROVAL_APPROVED"
    finally:
        app.dependency_overrides.clear()

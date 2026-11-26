"""Comprehensive automated evaluation test suite for SENTINEL-X.

Verifies the 10 core evaluation scenarios:
1. test_01_normal_delegation: Coordinator delegates to two specialist agents -> verifies lineage node/edge counts and SUCCEEDED status.
2. test_02_tool_failure: Tool span fails with ValueError -> verifies failed status and error_class preserved on exact node.
3. test_03_repeated_tool_loop: Agent emits 3+ identical tool signatures within time window -> verifies LOOP_DETECTED alert and acyclic nodes.
4. test_04_token_budget_overrun: Run exceeds RUN_TOKEN_BUDGET -> verifies BUDGET_EXCEEDED alert with observed token evidence.
5. test_05_stalled_run: Run has no terminal event past RUN_STALL_TIMEOUT_SEC -> watchdog transitions to STALLED (never SUCCEEDED) with alert.
6. test_06_cascading_failure: Upstream tool fails triggering downstream failures -> verifies CASCADE_FAILURE alert, is_root_cause=True on origin span.
7. test_07_approval_required_and_approved: Protected action enters AWAITING_APPROVAL, approver submits APPROVED -> verifies AuditEvent and span transitions to RUNNING.
8. test_08_approval_rejected_and_rbac: Viewer role gets 403 Forbidden, approver submits REJECTED -> marks REJECTED, span CANCELLED, persists AuditEvent.
9. test_09_cost_rollup_no_double_counting: Parent AGENT wraps two child LLM spans -> verifies total_cost_usd and rolled_up_cost_usd equal sum of child direct costs without duplication.
10. test_10_missing_usage_marked_unknown: LLM span emitted with usage=None -> verifies cost_basis=="UNKNOWN" and direct_cost_usd is None (never 0.0).
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import jwt
import pytest
from httpx import ASGITransport, AsyncClient
from sentinel_backend.config import settings
from sentinel_backend.db.session import get_db
from sentinel_backend.main import app
from sentinel_backend.models.alert import Alert
from sentinel_backend.models.approval import Approval
from sentinel_backend.models.audit import AuditEvent
from sentinel_backend.models.pricing import PricingVersion
from sentinel_backend.models.run import Run
from sentinel_backend.models.span import Span
from sentinel_backend.services.anomaly_engine import (
    check_stalled_runs,
    evaluate_run_anomalies,
)
from sentinel_backend.services.cost_calculator import calculate_run_costs


def _org_headers(actor_id: str = "eval-approver", role: str = "approver") -> dict[str, str]:
    token = jwt.encode(
        {
            "sub": actor_id,
            "email": actor_id,
            "name": actor_id,
            "role": role,
            "allowed_teams": ["*"],
            "is_demo": False,
            "exp": datetime.now(UTC) + timedelta(minutes=30),
        },
        settings.JWT_SECRET,
        algorithm="HS256",
    )
    return {"Authorization": f"Bearer {token}"}


class EvaluationMockDB:
    """In-memory mock session supporting AsyncSession protocols for FastAPI and domain services."""

    def __init__(
        self,
        runs: list[Run] | None = None,
        spans: list[Span] | None = None,
        alerts: list[Alert] | None = None,
        approvals: list[Approval] | None = None,
        audit_events: list[AuditEvent] | None = None,
        pricing: list[PricingVersion] | None = None,
    ) -> None:
        self.runs: dict[str, Run] = {r.run_id: r for r in (runs or [])}
        self.spans: dict[str, Span] = {s.span_id: s for s in (spans or [])}
        self.approvals: dict[str, Approval] = {a.approval_id: a for a in (approvals or [])}
        self.alerts: list[Alert] = list(alerts or [])
        self.audit_events: list[AuditEvent] = list(audit_events or [])
        self.pricing: list[PricingVersion] = list(pricing or [])

    async def get(self, entity: Any, ident: Any, *args: Any, **kwargs: Any) -> Any:
        if entity == Run:
            return self.runs.get(ident)
        if entity == Span:
            return self.spans.get(ident)
        if entity == Approval:
            return self.approvals.get(ident)
        if entity == PricingVersion:
            return next((p for p in self.pricing if p.id == ident), None)
        return None

    async def flush(self) -> None:
        pass

    def add(self, obj: Any) -> None:
        if isinstance(obj, Run):
            self.runs[obj.run_id] = obj
        elif isinstance(obj, Span):
            self.spans[obj.span_id] = obj
        elif isinstance(obj, Approval):
            self.approvals[obj.approval_id] = obj
        elif isinstance(obj, Alert):
            self.alerts.append(obj)
        elif isinstance(obj, AuditEvent):
            self.audit_events.append(obj)
        elif isinstance(obj, PricingVersion):
            if obj.id is None:
                obj.id = len(self.pricing) + 1
            self.pricing.append(obj)

    def add_all(self, objs: list[Any]) -> None:
        for o in objs:
            self.add(o)

    async def commit(self) -> None:
        pass

    async def refresh(self, obj: Any) -> None:
        if isinstance(obj, PricingVersion) and obj.id is None:
            obj.id = len(self.pricing) + 1

    async def execute(self, stmt: Any, *args: Any, **kwargs: Any) -> MagicMock:
        stmt_str = str(stmt).lower()
        res = MagicMock()

        if "from pricing_versions" in stmt_str:
            res.scalars.return_value.all.return_value = list(self.pricing)
            res.scalar_one_or_none.return_value = self.pricing[0] if self.pricing else None
            return res

        if "from audit_events" in stmt_str:
            ordered = sorted(self.audit_events, key=lambda a: a.created_at, reverse=True)
            res.scalars.return_value.all.return_value = ordered
            res.scalar_one_or_none.return_value = ordered[0] if ordered else None
            return res

        if "from alerts" in stmt_str:
            # During _upsert_alert query (WHERE rule_id == ... and origin_span_id == ...), return None to insert new
            if "rule_id" in stmt_str and "origin_span_id" in stmt_str:
                res.scalar_one_or_none.return_value = None
            else:
                res.scalar_one_or_none.return_value = self.alerts[0] if self.alerts else None
            res.scalars.return_value.all.return_value = list(self.alerts)
            return res

        if "from approvals" in stmt_str:
            approvals_list = list(self.approvals.values())
            if "with_for_update" in stmt_str or "approval_id" in stmt_str:
                res.scalar_one_or_none.return_value = approvals_list[0] if approvals_list else None
            else:
                # Initial existence check when creating approval
                res.scalar_one_or_none.return_value = None
            res.scalars.return_value.all.return_value = approvals_list
            return res

        if "from spans" in stmt_str:
            spans_list = list(self.spans.values())
            if "status" in stmt_str and ("running" in stmt_str or "queued" in stmt_str):
                matched = [s for s in spans_list if s.status in ("RUNNING", "QUEUED")]
                res.scalars.return_value.all.return_value = matched
                res.scalar_one_or_none.return_value = matched[0] if matched else None
            else:
                res.scalars.return_value.all.return_value = spans_list
                res.scalar_one_or_none.return_value = spans_list[0] if spans_list else None
            return res

        if "from runs" in stmt_str:
            runs_list = list(self.runs.values())
            res.scalars.return_value.all.return_value = runs_list
            res.scalar_one_or_none.return_value = runs_list[0] if runs_list else None
            return res

        res.scalars.return_value.all.return_value = []
        res.scalar_one_or_none.return_value = None
        return res


# ==============================================================================
# Scenario 1: Normal Multi-Agent Delegation
# ==============================================================================
@pytest.mark.asyncio
async def test_01_normal_delegation():
    """Coordinator delegates to two specialist agents.

    Verifies lineage returns exact parent-child node/edge counts (3 nodes, 2 edges)
    and terminal run status SUCCEEDED.
    """
    now = datetime.now(UTC)
    t0 = now - timedelta(seconds=10)
    t1 = now - timedelta(seconds=8)
    t2 = now - timedelta(seconds=4)
    t3 = now

    run = Run(
        run_id="run_eval_01",
        trace_id="trace_eval_01" + "0" * 19,
        root_agent_id="coordinator-agent",
        team="it-ops",
        status="SUCCEEDED",
        started_at=t0,
        ended_at=t3,
        last_event_at=t3,
        total_tokens=1200,
        total_cost_usd=0.015,
        cost_status="EXACT",
    )

    span_coord = Span(
        span_id="span_coord",
        trace_id=run.trace_id,
        parent_span_id=None,
        run_id=run.run_id,
        agent_id="coordinator-agent",
        attempt_number=1,
        span_type="AGENT",
        operation_name="coordinator_triage",
        status="SUCCEEDED",
        started_at=t0,
        ended_at=t3,
        attributes={"task": "triage_incident"},
    )

    span_spec1 = Span(
        span_id="span_spec1",
        trace_id=run.trace_id,
        parent_span_id="span_coord",
        run_id=run.run_id,
        agent_id="diagnostic-agent",
        attempt_number=1,
        span_type="AGENT",
        operation_name="diagnose_health",
        status="SUCCEEDED",
        started_at=t1,
        ended_at=t2,
        attributes={"subtask": "inspect_metrics"},
    )

    span_spec2 = Span(
        span_id="span_spec2",
        trace_id=run.trace_id,
        parent_span_id="span_coord",
        run_id=run.run_id,
        agent_id="remediation-agent",
        attempt_number=1,
        span_type="AGENT",
        operation_name="remediate_cache",
        status="SUCCEEDED",
        started_at=t2,
        ended_at=t3,
        attributes={"subtask": "evict_keys"},
    )

    mock_db = EvaluationMockDB(runs=[run], spans=[span_coord, span_spec1, span_spec2])
    app.dependency_overrides[get_db] = lambda: mock_db

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/runs/run_eval_01/lineage", headers=_org_headers())
            assert resp.status_code == 200
            data = resp.json()

            assert data["run_id"] == "run_eval_01"
            assert data["status"] == "SUCCEEDED"

            # Exact node and edge counts
            assert len(data["nodes"]) == 3
            assert len(data["edges"]) == 2

            node_ids = {node["id"] for node in data["nodes"]}
            assert node_ids == {"span_coord", "span_spec1", "span_spec2"}

            for node in data["nodes"]:
                assert node["status"] == "SUCCEEDED"

            # Parent-child lineage verification
            edge_pairs = {(e["source"], e["target"]) for e in data["edges"]}
            assert ("span_coord", "span_spec1") in edge_pairs
            assert ("span_coord", "span_spec2") in edge_pairs

            for edge in data["edges"]:
                assert edge["is_failed_path"] is False
    finally:
        app.dependency_overrides.clear()


# ==============================================================================
# Scenario 2: Tool Failure Attribution
# ==============================================================================
@pytest.mark.asyncio
async def test_02_tool_failure():
    """A tool span fails with ValueError.

    Verifies failed span status and error_class are preserved on the exact node.
    """
    now = datetime.now(UTC)
    t0 = now - timedelta(seconds=5)
    t1 = now

    run = Run(
        run_id="run_eval_02",
        trace_id="trace_eval_02" + "0" * 19,
        root_agent_id="coordinator-agent",
        team="it-ops",
        status="FAILED",
        started_at=t0,
        ended_at=t1,
        last_event_at=t1,
    )

    span_coord = Span(
        span_id="span_coord_fail",
        trace_id=run.trace_id,
        parent_span_id=None,
        run_id=run.run_id,
        agent_id="coordinator-agent",
        attempt_number=1,
        span_type="AGENT",
        operation_name="coordinator_triage",
        status="FAILED",
        started_at=t0,
        ended_at=t1,
    )

    span_tool = Span(
        span_id="span_tool_corrupt",
        trace_id=run.trace_id,
        parent_span_id="span_coord_fail",
        run_id=run.run_id,
        agent_id="diagnostic-agent",
        attempt_number=1,
        span_type="TOOL",
        operation_name="fetch_corrupt_config",
        status="FAILED",
        error_class="ValueError",
        error_message="Malformed JSON schema in cluster config",
        started_at=t0 + timedelta(seconds=1),
        ended_at=t1,
        attributes={"inputs": {"config_path": "/etc/cluster/config.json"}},
    )

    mock_db = EvaluationMockDB(runs=[run], spans=[span_coord, span_tool])
    app.dependency_overrides[get_db] = lambda: mock_db

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/runs/run_eval_02/lineage", headers=_org_headers())
            assert resp.status_code == 200
            data = resp.json()

            assert data["run_id"] == "run_eval_02"
            assert data["status"] == "FAILED"

            # Locate the exact failed tool node
            tool_node = next((n for n in data["nodes"] if n["id"] == "span_tool_corrupt"), None)
            assert tool_node is not None
            assert tool_node["status"] == "FAILED"
            assert tool_node["error_class"] == "ValueError"
            assert tool_node["error_message"] == "Malformed JSON schema in cluster config"
            assert tool_node["operation_name"] == "fetch_corrupt_config"
            assert tool_node["span_type"] == "TOOL"

            # Incoming edge to failed tool must have is_failed_path = True
            tool_edge = next((e for e in data["edges"] if e["target"] == "span_tool_corrupt"), None)
            assert tool_edge is not None
            assert tool_edge["is_failed_path"] is True
    finally:
        app.dependency_overrides.clear()


# ==============================================================================
# Scenario 3: Repeated Tool Loop Detection
# ==============================================================================
@pytest.mark.asyncio
async def test_03_repeated_tool_loop():
    """Agent emits 3+ identical tool signatures within the time window.

    Verifies LOOP_DETECTED alert fires with evidence and acyclic attempt_number nodes.
    """
    now = datetime.now(UTC)
    run = Run(
        run_id="run_eval_03",
        trace_id="trace_eval_03" + "0" * 19,
        root_agent_id="remediation-agent",
        team="it-ops",
        status="RUNNING",
        started_at=now - timedelta(seconds=30),
        last_event_at=now,
    )

    # 4 consecutive executions of query_flaky_endpoint with identical inputs
    tool_spans: list[Span] = []
    for i in range(1, 5):
        s = Span(
            span_id=f"span_loop_probe_{i}",
            trace_id=run.trace_id,
            parent_span_id=None,
            run_id=run.run_id,
            agent_id="remediation-agent",
            attempt_number=i,
            span_type="TOOL",
            operation_name="query_flaky_endpoint",
            status="SUCCEEDED",
            started_at=now - timedelta(seconds=25 - (i * 4)),
            ended_at=now - timedelta(seconds=24 - (i * 4)),
            attributes={"inputs": {"url": "https://api.internal/health"}},
        )
        tool_spans.append(s)

    mock_db = EvaluationMockDB(runs=[run], spans=tool_spans)
    app.dependency_overrides[get_db] = lambda: mock_db

    try:
        with patch("sentinel_backend.services.anomaly_engine.publish_event", new_callable=AsyncMock):
            alerts = await evaluate_run_anomalies(mock_db, "run_eval_03")

            assert len(alerts) == 1
            alert = alerts[0]
            assert alert.rule_id == "LOOP_DETECTED"
            assert alert.severity == "HIGH"
            assert alert.evidence["tool_name"] == "query_flaky_endpoint"
            assert alert.evidence["repeat_count"] == 4
            assert alert.evidence["threshold"] == settings.LOOP_THRESHOLD_COUNT
            assert alert.origin_span_id == "span_loop_probe_1"
            assert len(alert.impacted_span_ids) == 4

        # Verify via REST API: GET /api/alerts?run_id=run_eval_03
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp_alerts = await client.get(
                "/api/alerts?run_id=run_eval_03",
                headers=_org_headers(),
            )
            assert resp_alerts.status_code == 200
            alert_items = resp_alerts.json()
            assert len(alert_items) == 1
            assert alert_items[0]["rule_id"] == "LOOP_DETECTED"
            assert alert_items[0]["evidence"]["repeat_count"] == 4

            # Verify Lineage keeps acyclic attempt_number nodes
            resp_lineage = await client.get(
                "/api/runs/run_eval_03/lineage",
                headers=_org_headers(),
            )
            assert resp_lineage.status_code == 200
            lineage_data = resp_lineage.json()

            assert len(lineage_data["nodes"]) == 4
            attempts = [n["attempt_number"] for n in lineage_data["nodes"]]
            assert attempts == [1, 2, 3, 4]
    finally:
        app.dependency_overrides.clear()


# ==============================================================================
# Scenario 4: Token Budget Overrun Detection
# ==============================================================================
@pytest.mark.asyncio
async def test_04_token_budget_overrun():
    """Run exceeds RUN_TOKEN_BUDGET.

    Verifies BUDGET_EXCEEDED alert fires with observed token evidence.
    """
    now = datetime.now(UTC)
    run = Run(
        run_id="run_eval_04",
        trace_id="trace_eval_04" + "0" * 19,
        root_agent_id="verbose-agent",
        team="it-ops",
        status="RUNNING",
        started_at=now - timedelta(seconds=20),
        last_event_at=now,
        total_tokens=7500,
    )

    span_llm_1 = Span(
        span_id="span_llm_chunk_1",
        trace_id=run.trace_id,
        parent_span_id=None,
        run_id=run.run_id,
        agent_id="verbose-agent",
        attempt_number=1,
        span_type="LLM",
        operation_name="gpt-4o",
        status="SUCCEEDED",
        started_at=now - timedelta(seconds=15),
        input_tokens=4000,
        output_tokens=1500,  # 5500 tokens
    )

    span_llm_2 = Span(
        span_id="span_llm_chunk_2",
        trace_id=run.trace_id,
        parent_span_id=None,
        run_id=run.run_id,
        agent_id="verbose-agent",
        attempt_number=1,
        span_type="LLM",
        operation_name="gpt-4o",
        status="SUCCEEDED",
        started_at=now - timedelta(seconds=8),
        input_tokens=1500,
        output_tokens=500,  # 2000 tokens
    )

    mock_db = EvaluationMockDB(runs=[run], spans=[span_llm_1, span_llm_2])
    app.dependency_overrides[get_db] = lambda: mock_db

    try:
        with patch("sentinel_backend.services.anomaly_engine.publish_event", new_callable=AsyncMock):
            alerts = await evaluate_run_anomalies(mock_db, "run_eval_04")

            assert len(alerts) == 1
            alert = alerts[0]
            assert alert.rule_id == "BUDGET_EXCEEDED"
            assert alert.severity == "HIGH"
            assert alert.origin_span_id == "span_llm_chunk_1"  # Highest token span (5500)
            assert alert.evidence["total_tokens"] == 7500
            assert alert.evidence["budget_limit"] == settings.RUN_TOKEN_BUDGET
            assert "span_llm_chunk_1" in alert.impacted_span_ids
            assert "span_llm_chunk_2" in alert.impacted_span_ids

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/alerts?run_id=run_eval_04")
            assert resp.status_code == 200
            items = resp.json()
            assert len(items) == 1
            assert items[0]["rule_id"] == "BUDGET_EXCEEDED"
            assert items[0]["evidence"]["total_tokens"] == 7500
    finally:
        app.dependency_overrides.clear()


# ==============================================================================
# Scenario 5: Stalled Run Watchdog Detection
# ==============================================================================
@pytest.mark.asyncio
async def test_05_stalled_run():
    """Run has no terminal event past RUN_STALL_TIMEOUT_SEC.

    Invoking the watchdog check transitions run to STALLED and creates RUN_STALLED alert
    (never falsely SUCCEEDED).
    """
    now = datetime.now(UTC)
    stalled_run = Run(
        run_id="run_eval_05",
        trace_id="trace_eval_05" + "0" * 19,
        root_agent_id="coordinator-agent",
        team="it-ops",
        status="RUNNING",
        started_at=now - timedelta(seconds=60),
        last_event_at=now - timedelta(seconds=35),  # > 25s threshold
        total_tokens=200,
        cost_status="EXACT",
    )

    open_span = Span(
        span_id="span_open_active",
        trace_id=stalled_run.trace_id,
        run_id=stalled_run.run_id,
        agent_id="coordinator-agent",
        operation_name="coordinator_triage",
        span_type="AGENT",
        status="RUNNING",
        started_at=stalled_run.started_at,
    )

    mock_db = EvaluationMockDB(runs=[stalled_run], spans=[open_span])
    app.dependency_overrides[get_db] = lambda: mock_db

    try:
        with patch("sentinel_backend.services.anomaly_engine.publish_event", new_callable=AsyncMock):
            alerts = await check_stalled_runs(mock_db)

            assert len(alerts) == 1
            alert = alerts[0]
            assert alert.rule_id == "RUN_STALLED"
            assert alert.severity == "MEDIUM"
            assert alert.run_id == "run_eval_05"
            assert alert.origin_span_id == "span_open_active"

            # Verify run state mutated to STALLED and terminal time set (never SUCCEEDED)
            assert stalled_run.status == "STALLED"
            assert stalled_run.status != "SUCCEEDED"
            assert stalled_run.ended_at is not None
            assert open_span.status == "STALLED"
            assert open_span.error_class == "StallTimeoutError"

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/alerts?run_id=run_eval_05")
            assert resp.status_code == 200
            items = resp.json()
            assert len(items) == 1
            assert items[0]["rule_id"] == "RUN_STALLED"
            assert items[0]["severity"] == "MEDIUM"
    finally:
        app.dependency_overrides.clear()


# ==============================================================================
# Scenario 6: Cascading Failure & Root Cause Attribution
# ==============================================================================
@pytest.mark.asyncio
async def test_06_cascading_failure():
    """Upstream tool fails and triggers downstream specialist/coordinator failures.

    Verifies CASCADE_FAILURE alert sets is_root_cause=True on the upstream origin span
    and lists downstream descendants in impacted_span_ids.
    """
    now = datetime.now(UTC)
    run = Run(
        run_id="run_eval_06",
        trace_id="trace_eval_06" + "0" * 19,
        root_agent_id="coordinator-agent",
        team="it-ops",
        status="FAILED",
        started_at=now - timedelta(seconds=20),
        last_event_at=now,
    )

    # Hierarchical chain: Coordinator -> Diagnostic Agent -> Corrupt Tool
    span_coord = Span(
        span_id="span_coord_root",
        trace_id=run.trace_id,
        parent_span_id=None,
        run_id=run.run_id,
        agent_id="coordinator-agent",
        span_type="AGENT",
        operation_name="coordinator_triage",
        status="FAILED",
        started_at=now - timedelta(seconds=20),
        error_class="RuntimeError",
        error_message="Sub-workflow execution failed",
    )

    span_diag = Span(
        span_id="span_diag_agent",
        trace_id=run.trace_id,
        parent_span_id="span_coord_root",
        run_id=run.run_id,
        agent_id="diagnostic-agent",
        span_type="AGENT",
        operation_name="diagnose_system",
        status="FAILED",
        started_at=now - timedelta(seconds=15),
        error_class="RuntimeError",
        error_message="Configuration probe failed",
    )

    span_tool_origin = Span(
        span_id="span_tool_origin",
        trace_id=run.trace_id,
        parent_span_id="span_diag_agent",
        run_id=run.run_id,
        agent_id="diagnostic-agent",
        span_type="TOOL",
        operation_name="fetch_corrupt_config",
        status="FAILED",
        started_at=now - timedelta(seconds=10),
        error_class="ValueError",
        error_message="Malformed JSON schema in cluster config",
    )

    mock_db = EvaluationMockDB(runs=[run], spans=[span_coord, span_diag, span_tool_origin])
    app.dependency_overrides[get_db] = lambda: mock_db

    try:
        with patch("sentinel_backend.services.anomaly_engine.publish_event", new_callable=AsyncMock):
            alerts = await evaluate_run_anomalies(mock_db, "run_eval_06")

            assert len(alerts) == 1
            alert = alerts[0]
            assert alert.rule_id == "CASCADE_FAILURE"
            assert alert.severity == "CRITICAL"

            # Root cause attribution on deepest upstream origin failure
            assert alert.origin_span_id == "span_tool_origin"
            assert span_tool_origin.is_root_cause is True
            assert span_coord.is_root_cause is False
            assert span_diag.is_root_cause is False

            # Impacted span IDs include the origin and affected downstream spans
            assert "span_tool_origin" in alert.impacted_span_ids
            assert "span_diag_agent" in alert.impacted_span_ids
            assert "span_coord_root" in alert.impacted_span_ids

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/alerts?run_id=run_eval_06")
            assert resp.status_code == 200
            items = resp.json()
            assert len(items) == 1
            assert items[0]["rule_id"] == "CASCADE_FAILURE"
            assert items[0]["origin_span_id"] == "span_tool_origin"
    finally:
        app.dependency_overrides.clear()


# ==============================================================================
# Scenario 7: Approval Required and Approved (HITL Gate)
# ==============================================================================
@pytest.mark.asyncio
async def test_07_approval_required_and_approved():
    """Protected action enters AWAITING_APPROVAL, blocks until an approver submits APPROVED.

    Verifies AuditEvent is recorded and span transitions to RUNNING/SUCCEEDED.
    """
    now = datetime.now(UTC)
    run = Run(
        run_id="run_eval_07",
        trace_id="trace_eval_07" + "0" * 19,
        root_agent_id="remediation-agent",
        team="it-ops",
        status="RUNNING",
        started_at=now - timedelta(seconds=10),
        last_event_at=now,
    )

    span = Span(
        span_id="span_gate_cluster_restart",
        trace_id=run.trace_id,
        parent_span_id=None,
        run_id=run.run_id,
        agent_id="critical-remediation-agent",
        attempt_number=1,
        span_type="TOOL",
        operation_name="restart_production_cluster",
        status="RUNNING",
        started_at=now - timedelta(seconds=5),
        attributes={"inputs": {"cluster": "primary-postgres"}},
    )

    mock_db = EvaluationMockDB(runs=[run], spans=[span])
    app.dependency_overrides[get_db] = lambda: mock_db

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # 1. SDK / Agent submits approval request for gated critical tool
            req_body = {
                "run_id": "run_eval_07",
                "span_id": "span_gate_cluster_restart",
                "agent_id": "critical-remediation-agent",
                "tool_name": "restart_production_cluster",
                "sanitized_args": {"cluster": "primary-postgres"},
                "risk_level": "CRITICAL",
                "policy_reason": "Production database cluster restart impacts customer traffic",
            }
            with patch("sentinel_backend.services.governance.publish_event", new_callable=AsyncMock):
                resp_req = await client.post(
                    "/api/approvals/request",
                    headers={"X-API-Key": settings.SENTINEL_API_KEY},
                    json=req_body,
                )
                assert resp_req.status_code == 200
                appr_data = resp_req.json()
                approval_id = appr_data["approval_id"]
                assert appr_data["status"] == "PENDING"
                assert span.status == "AWAITING_APPROVAL"
                assert run.status == "AWAITING_APPROVAL"

            # 2. Authorized human approver submits APPROVED decision
            decision_body = {
                "decision": "APPROVED",
                "comment": "Authorized failover per incident ticket #9821",
            }
            with patch("sentinel_backend.services.governance.publish_event", new_callable=AsyncMock):
                resp_dec = await client.post(
                    f"/api/approvals/{approval_id}/decision",
                    headers=_org_headers("lead-sre-alice", "approver"),
                    json=decision_body,
                )
                assert resp_dec.status_code == 200
                dec_data = resp_dec.json()
                assert dec_data["status"] == "APPROVED"
                assert dec_data["decided_by"] == "lead-sre-alice"
                assert span.status == "RUNNING"
                assert run.status == "RUNNING"

            # 3. Verify append-only AuditEvent log
            resp_audit = await client.get("/api/audit-events", headers=_org_headers())
            assert resp_audit.status_code == 200
            audit_events = resp_audit.json()
            assert len(audit_events) >= 1
            approved_event = next((e for e in audit_events if e["action"] == "APPROVAL_APPROVED"), None)
            assert approved_event is not None
            assert approved_event["actor_id"] == "lead-sre-alice"
            assert approved_event["actor_role"] == "approver"
            assert approved_event["target_id"] == approval_id
    finally:
        app.dependency_overrides.clear()


# ==============================================================================
# Scenario 8: Approval Rejected and RBAC Enforcement
# ==============================================================================
@pytest.mark.asyncio
async def test_08_approval_rejected_and_rbac():
    """Verifies viewer role gets 403 Forbidden.

    When an approver submits REJECTED, the approval is marked REJECTED, span becomes
    CANCELLED, and an immutable AuditEvent is persisted.
    """
    now = datetime.now(UTC)
    run = Run(
        run_id="run_eval_08",
        trace_id="trace_eval_08" + "0" * 19,
        root_agent_id="remediation-agent",
        team="it-ops",
        status="AWAITING_APPROVAL",
        started_at=now - timedelta(seconds=10),
        last_event_at=now,
    )

    span = Span(
        span_id="span_gate_drop_cache",
        trace_id=run.trace_id,
        parent_span_id=None,
        run_id=run.run_id,
        agent_id="remediation-agent",
        attempt_number=1,
        span_type="TOOL",
        operation_name="flush_all_keys",
        status="AWAITING_APPROVAL",
        started_at=now - timedelta(seconds=5),
        attributes={"inputs": {"scope": "global"}},
    )

    approval = Approval(
        approval_id="apr_eval_08_reject",
        run_id=run.run_id,
        span_id=span.span_id,
        agent_id=span.agent_id,
        tool_name="flush_all_keys",
        sanitized_args={"scope": "global"},
        risk_level="CRITICAL",
        policy_reason="Global cache flush risks cache stampede",
        status="PENDING",
        created_at=now,
    )

    mock_db = EvaluationMockDB(runs=[run], spans=[span], approvals=[approval])
    app.dependency_overrides[get_db] = lambda: mock_db

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # 1. RBAC Check: viewer role must get 403 Forbidden
            resp_rbac = await client.post(
                "/api/approvals/apr_eval_08_reject/decision",
                headers=_org_headers("guest-observer", "viewer"),
                json={"decision": "REJECTED", "comment": "Trying to decide as viewer"},
            )
            assert resp_rbac.status_code == 403
            assert "approver privileges" in resp_rbac.json()["detail"]

            # 2. Authorized approver rejects the destructive action
            with patch("sentinel_backend.services.governance.publish_event", new_callable=AsyncMock):
                resp_dec = await client.post(
                    "/api/approvals/apr_eval_08_reject/decision",
                    headers=_org_headers("security-officer-dan", "approver"),
                    json={"decision": "REJECTED", "comment": "Unsafe global flush blocked"},
                )
                assert resp_dec.status_code == 200
                dec_data = resp_dec.json()
                assert dec_data["status"] == "REJECTED"
                assert dec_data["decided_by"] == "security-officer-dan"

                # Associated span transitions to CANCELLED
                assert span.status == "CANCELLED"

            # 3. Verify immutable AuditEvent
            resp_audit = await client.get("/api/audit-events", headers=_org_headers())
            assert resp_audit.status_code == 200
            audit_events = resp_audit.json()
            rejected_event = next((e for e in audit_events if e["action"] == "APPROVAL_REJECTED"), None)
            assert rejected_event is not None
            assert rejected_event["actor_id"] == "security-officer-dan"
            assert rejected_event["actor_role"] == "approver"
            assert rejected_event["target_id"] == "apr_eval_08_reject"
    finally:
        app.dependency_overrides.clear()


# ==============================================================================
# Scenario 9: Versioned Cost Attribution (No Double-Counting)
# ==============================================================================
@pytest.mark.asyncio
async def test_09_cost_rollup_no_double_counting():
    """Parent AGENT span wraps two child LLM spans.

    Verifies run.total_cost_usd and parent node rolled_up_cost_usd equal the exact
    sum of the two child LLM direct costs without duplication.
    """
    now = datetime.now(UTC)
    run = Run(
        run_id="run_eval_09",
        trace_id="trace_eval_09" + "0" * 19,
        root_agent_id="coordinator-agent",
        team="ai-platform",
        status="SUCCEEDED",
        started_at=now - timedelta(seconds=10),
        ended_at=now,
        last_event_at=now,
        total_tokens=4500,
    )

    pricing_gpt4o = PricingVersion(
        id=1,
        provider="openai",
        model_name="gpt-4o",
        version_tag="2026-11-v1",
        input_rate_per_1m=Decimal("2.50"),
        output_rate_per_1m=Decimal("10.00"),
        effective_from=now - timedelta(days=1),
    )
    pricing_gpt4o_mini = PricingVersion(
        id=2,
        provider="openai",
        model_name="gpt-4o-mini",
        version_tag="2026-11-v1",
        input_rate_per_1m=Decimal("0.15"),
        output_rate_per_1m=Decimal("0.60"),
        effective_from=now - timedelta(days=1),
    )

    span_agent = Span(
        span_id="span_agent_parent",
        trace_id=run.trace_id,
        parent_span_id=None,
        run_id=run.run_id,
        agent_id="coordinator-agent",
        attempt_number=1,
        span_type="AGENT",
        operation_name="coordinator_pipeline",
        status="SUCCEEDED",
        started_at=now - timedelta(seconds=10),
        ended_at=now,
    )

    # Child 1: LLM gpt-4o (1000 input, 500 output)
    # direct_cost = (1000 * 2.50 + 500 * 10.00) / 1,000,000 = 7500 / 1e6 = 0.0075
    span_llm_1 = Span(
        span_id="span_llm_child_1",
        trace_id=run.trace_id,
        parent_span_id="span_agent_parent",
        run_id=run.run_id,
        agent_id="coordinator-agent",
        attempt_number=1,
        span_type="LLM",
        operation_name="plan_generation",
        model_provider="openai",
        model_name="gpt-4o",
        input_tokens=1000,
        output_tokens=500,
        status="SUCCEEDED",
        started_at=now - timedelta(seconds=8),
        ended_at=now - timedelta(seconds=5),
    )

    # Child 2: LLM gpt-4o-mini (2000 input, 1000 output)
    # direct_cost = (2000 * 0.15 + 1000 * 0.60) / 1,000,000 = 900 / 1e6 = 0.0009
    span_llm_2 = Span(
        span_id="span_llm_child_2",
        trace_id=run.trace_id,
        parent_span_id="span_agent_parent",
        run_id=run.run_id,
        agent_id="coordinator-agent",
        attempt_number=1,
        span_type="LLM",
        operation_name="summarize_output",
        model_provider="openai",
        model_name="gpt-4o-mini",
        input_tokens=2000,
        output_tokens=1000,
        status="SUCCEEDED",
        started_at=now - timedelta(seconds=4),
        ended_at=now - timedelta(seconds=1),
    )

    mock_db = EvaluationMockDB(
        runs=[run],
        spans=[span_agent, span_llm_1, span_llm_2],
        pricing=[pricing_gpt4o, pricing_gpt4o_mini],
    )
    app.dependency_overrides[get_db] = lambda: mock_db

    try:
        # Calculate costs via service
        await calculate_run_costs(mock_db, "run_eval_09")

        # 1. Non-leaf AGENT span keeps direct_cost_usd = None
        assert span_agent.direct_cost_usd is None

        # 2. Leaf LLM spans have exact direct costs
        assert float(span_llm_1.direct_cost_usd) == pytest.approx(0.0075)
        assert span_llm_1.cost_basis == "EXACT"

        assert float(span_llm_2.direct_cost_usd) == pytest.approx(0.0009)
        assert span_llm_2.cost_basis == "EXACT"

        # 3. Run total cost equals exact sum (0.0075 + 0.0009 = 0.0084)
        assert float(run.total_cost_usd) == pytest.approx(0.0084)
        assert run.cost_status == "EXACT"

        # 4. Verify Lineage DAG rolled_up_cost_usd via REST API
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/runs/run_eval_09/lineage", headers=_org_headers())
            assert resp.status_code == 200
            data = resp.json()

            parent_node = next((n for n in data["nodes"] if n["id"] == "span_agent_parent"), None)
            assert parent_node is not None
            assert parent_node["direct_cost_usd"] is None
            # Subtree roll-up on parent node must equal exact sum of descendants
            assert parent_node["rolled_up_cost_usd"] == pytest.approx(0.0084)

            child_1_node = next((n for n in data["nodes"] if n["id"] == "span_llm_child_1"), None)
            assert child_1_node is not None
            assert child_1_node["direct_cost_usd"] == pytest.approx(0.0075)
            assert child_1_node["rolled_up_cost_usd"] == pytest.approx(0.0075)

            child_2_node = next((n for n in data["nodes"] if n["id"] == "span_llm_child_2"), None)
            assert child_2_node is not None
            assert child_2_node["direct_cost_usd"] == pytest.approx(0.0009)
            assert child_2_node["rolled_up_cost_usd"] == pytest.approx(0.0009)
    finally:
        app.dependency_overrides.clear()


# ==============================================================================
# Scenario 10: Missing Token Usage Marked UNKNOWN
# ==============================================================================
@pytest.mark.asyncio
async def test_10_missing_usage_marked_unknown():
    """LLM span emitted with usage=None.

    Verifies cost_basis == 'UNKNOWN' and direct_cost_usd is None (never 0.0).
    """
    now = datetime.now(UTC)
    run = Run(
        run_id="run_eval_10",
        trace_id="trace_eval_10" + "0" * 19,
        root_agent_id="test-agent",
        team="ai-platform",
        status="RUNNING",
        started_at=now - timedelta(seconds=5),
        last_event_at=now,
    )

    pricing_gpt4o = PricingVersion(
        id=1,
        provider="openai",
        model_name="gpt-4o",
        version_tag="2026-11-v1",
        input_rate_per_1m=Decimal("2.50"),
        output_rate_per_1m=Decimal("10.00"),
        effective_from=now - timedelta(days=1),
    )

    # LLM span with missing usage telemetry (provider did not return token metrics)
    span_llm_unknown = Span(
        span_id="span_llm_missing_tokens",
        trace_id=run.trace_id,
        parent_span_id=None,
        run_id=run.run_id,
        agent_id="test-agent",
        attempt_number=1,
        span_type="LLM",
        operation_name="stream_chat",
        model_provider="openai",
        model_name="gpt-4o",
        input_tokens=None,
        output_tokens=None,
        status="SUCCEEDED",
        started_at=now - timedelta(seconds=4),
        ended_at=now - timedelta(seconds=1),
    )

    mock_db = EvaluationMockDB(
        runs=[run],
        spans=[span_llm_unknown],
        pricing=[pricing_gpt4o],
    )
    app.dependency_overrides[get_db] = lambda: mock_db

    try:
        await calculate_run_costs(mock_db, "run_eval_10")

        # Must strictly be None, NEVER substituted with 0.0
        assert span_llm_unknown.direct_cost_usd is None
        assert span_llm_unknown.direct_cost_usd != 0.0
        assert span_llm_unknown.cost_basis == "UNKNOWN"

        # Run level status must be UNKNOWN
        assert run.total_cost_usd is None
        assert run.cost_status == "UNKNOWN"

        # Verify Lineage node preserves UNKNOWN cost basis and None direct cost
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/runs/run_eval_10/lineage", headers=_org_headers())
            assert resp.status_code == 200
            data = resp.json()

            node = next((n for n in data["nodes"] if n["id"] == "span_llm_missing_tokens"), None)
            assert node is not None
            assert node["cost_basis"] == "UNKNOWN"
            assert node["direct_cost_usd"] is None
            assert node["rolled_up_cost_usd"] is None
    finally:
        app.dependency_overrides.clear()

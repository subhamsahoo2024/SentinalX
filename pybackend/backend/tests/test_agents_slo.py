from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient
from sentinel_backend.api.agents import _percentile
from sentinel_backend.db.session import get_db
from sentinel_backend.main import app
from sentinel_backend.models.agent import Agent
from sentinel_backend.models.alert import Alert
from sentinel_backend.models.span import Span
from sentinel_backend.schemas.telemetry import AgentSloDTO

# ==============================================================================
# Unit Tests: _percentile Helper
# ==============================================================================


def test_percentile_empty_list():
    assert _percentile([], 50.0) is None
    assert _percentile([], 95.0) is None


def test_percentile_single_item():
    values = [42.0]
    assert _percentile(values, 0.0) == 42.0
    assert _percentile(values, 50.0) == 42.0
    assert _percentile(values, 95.0) == 42.0
    assert _percentile(values, 100.0) == 42.0


def test_percentile_ten_items():
    values = [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0, 100.0]
    # pct 50: ceil(5.0) - 1 = 4 -> values[4] = 50.0
    assert _percentile(values, 50.0) == 50.0
    # pct 95: ceil(9.5) - 1 = 10 - 1 = 9 -> values[9] = 100.0
    assert _percentile(values, 95.0) == 100.0
    # pct 25: ceil(2.5) - 1 = 3 - 1 = 2 -> values[2] = 30.0
    assert _percentile(values, 25.0) == 30.0


def test_percentile_rounds_two_decimals():
    values = [10.12345, 20.98765]
    assert _percentile(values, 50.0) == 10.12
    assert _percentile(values, 95.0) == 20.99


# ==============================================================================
# API Tests: GET /api/agents/slos
# ==============================================================================


@pytest.mark.asyncio
async def test_get_agents_slos_endpoint():
    now = datetime.now(UTC)

    # 3 Agents
    agent1 = Agent(
        agent_id="agent_triage",
        display_name="Triage Coordinator",
        framework="custom",
        team="it-ops",
        environment="production",
        declared_tools=[],
        status="ACTIVE",
        last_seen_at=now,
    )
    agent2 = Agent(
        agent_id="agent_remediation",
        display_name="Remediation Bot",
        framework="langchain",
        team="it-ops",
        environment="production",
        declared_tools=[],
        status="ACTIVE",
        last_seen_at=now,
    )
    agent3 = Agent(
        agent_id="agent_idle",
        display_name="Idle Observer",
        framework="custom",
        team="sec-ops",
        environment="development",
        declared_tools=[],
        status="IDLE",
        last_seen_at=now,
    )

    # Spans for agent1: 3 spans (2 succeeded, 1 failed)
    span1 = Span(
        span_id="span_1",
        trace_id="trace_1",
        run_id="run_1",
        agent_id="agent_triage",
        span_type="AGENT",
        operation_name="triage_issue",
        status="SUCCEEDED",
        started_at=now,
        ended_at=now + timedelta(milliseconds=200),
        input_tokens=100,
        output_tokens=50,
        attributes={},
    )
    span2 = Span(
        span_id="span_2",
        trace_id="trace_1",
        run_id="run_1",
        agent_id="agent_triage",
        span_type="AGENT",
        operation_name="triage_issue",
        status="SUCCEEDED",
        started_at=now,
        ended_at=now + timedelta(milliseconds=400),
        input_tokens=150,
        output_tokens=50,
        attributes={},
    )
    span3 = Span(
        span_id="span_3",
        trace_id="trace_2",
        run_id="run_2",
        agent_id="agent_triage",
        span_type="AGENT",
        operation_name="triage_issue",
        status="FAILED",
        started_at=now,
        ended_at=now + timedelta(milliseconds=600),
        input_tokens=200,
        output_tokens=100,
        attributes={},
    )

    # Spans for agent2: 1 span (succeeded, rolled-up tokens in attributes)
    span4 = Span(
        span_id="span_4",
        trace_id="trace_3",
        run_id="run_3",
        agent_id="agent_remediation",
        span_type="AGENT",
        operation_name="restart_service",
        status="SUCCEEDED",
        started_at=now,
        ended_at=now + timedelta(milliseconds=150),
        input_tokens=0,
        output_tokens=0,
        attributes={"total_tokens": 500},
    )

    # Alert tied to span1 of agent1
    alert1 = Alert(
        alert_id="alert_1",
        run_id="run_1",
        origin_span_id="span_1",
        rule_id="LOOP_DETECTED",
        severity="HIGH",
        title="Loop in triage",
        evidence={},
        impacted_span_ids=["span_1"],
        acknowledged=False,
        created_at=now,
    )

    mock_db = AsyncMock()

    # Mock DB query executions in sequence:
    # 1. select(Agent)
    # 2. select(Span).where(Span.span_type == "AGENT")
    # 3. select(Alert)
    mock_agents_res = MagicMock()
    mock_agents_res.scalars.return_value.all.return_value = [agent1, agent2, agent3]

    mock_spans_res = MagicMock()
    mock_spans_res.scalars.return_value.all.return_value = [span1, span2, span3, span4]

    mock_alerts_res = MagicMock()
    mock_alerts_res.scalars.return_value.all.return_value = [alert1]

    mock_db.execute.side_effect = [
        mock_agents_res,
        mock_spans_res,
        mock_alerts_res,
    ]

    app.dependency_overrides[get_db] = lambda: mock_db

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/agents/slos")
            assert resp.status_code == 200
            data = resp.json()

            # Should return 3 agents sorted by total_invocations DESC
            assert len(data) == 3

            # 1st: agent_triage (3 invocations)
            slo1 = data[0]
            assert slo1["agent_id"] == "agent_triage"
            assert slo1["display_name"] == "Triage Coordinator"
            assert slo1["framework"] == "custom"
            assert slo1["team"] == "it-ops"
            assert slo1["total_invocations"] == 3
            assert slo1["succeeded_count"] == 2
            assert slo1["failed_count"] == 1
            assert slo1["success_rate_pct"] == 66.7
            assert slo1["p50_duration_ms"] == 400.0
            assert slo1["p95_duration_ms"] == 600.0
            # Token sum = 150 + 200 + 300 = 650. Avg = 650 / 3 = 216.7
            assert slo1["avg_tokens_per_call"] == 216.7
            assert slo1["anomaly_count"] == 1

            # 2nd: agent_remediation (1 invocation)
            slo2 = data[1]
            assert slo2["agent_id"] == "agent_remediation"
            assert slo2["display_name"] == "Remediation Bot"
            assert slo2["framework"] == "langchain"
            assert slo2["team"] == "it-ops"
            assert slo2["total_invocations"] == 1
            assert slo2["succeeded_count"] == 1
            assert slo2["failed_count"] == 0
            assert slo2["success_rate_pct"] == 100.0
            assert slo2["p50_duration_ms"] == 150.0
            assert slo2["p95_duration_ms"] == 150.0
            assert slo2["avg_tokens_per_call"] == 500.0
            assert slo2["anomaly_count"] == 0

            # 3rd: agent_idle (0 invocations)
            slo3 = data[2]
            assert slo3["agent_id"] == "agent_idle"
            assert slo3["display_name"] == "Idle Observer"
            assert slo3["team"] == "sec-ops"
            assert slo3["total_invocations"] == 0
            assert slo3["succeeded_count"] == 0
            assert slo3["failed_count"] == 0
            assert slo3["success_rate_pct"] == 100.0
            assert slo3["p50_duration_ms"] is None
            assert slo3["p95_duration_ms"] is None
            assert slo3["avg_tokens_per_call"] == 0.0
            assert slo3["anomaly_count"] == 0

            # Validate Pydantic schema validation for all returned items
            for item in data:
                AgentSloDTO.model_validate(item)

    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.mark.asyncio
async def test_get_agents_slos_alert_evidence_fallback():
    now = datetime.now(UTC)
    agent = Agent(
        agent_id="agent_diag",
        display_name="Diagnostic Agent",
        framework="custom",
        team="it-ops",
        environment="production",
        declared_tools=[],
        status="ACTIVE",
        last_seen_at=now,
    )
    # Span is for agent_diag
    span = Span(
        span_id="span_agent_diag",
        trace_id="trace_diag",
        run_id="run_diag",
        agent_id="agent_diag",
        span_type="AGENT",
        operation_name="diagnose",
        status="SUCCEEDED",
        started_at=now,
        ended_at=now + timedelta(milliseconds=100),
        input_tokens=50,
        output_tokens=20,
        attributes={},
    )
    # Alert with origin_span_id pointing to a tool span not in AGENT spans, but evidence has origin_agent
    alert = Alert(
        alert_id="alert_cascade",
        run_id="run_diag",
        origin_span_id="span_tool_not_in_agent_spans",
        rule_id="CASCADE_FAILURE",
        severity="CRITICAL",
        title="Cascade error",
        evidence={"origin_agent": "agent_diag"},
        impacted_span_ids=[],
        acknowledged=False,
        created_at=now,
    )

    mock_db = AsyncMock()
    mock_agents_res = MagicMock()
    mock_agents_res.scalars.return_value.all.return_value = [agent]
    mock_spans_res = MagicMock()
    mock_spans_res.scalars.return_value.all.return_value = [span]
    mock_alerts_res = MagicMock()
    mock_alerts_res.scalars.return_value.all.return_value = [alert]

    mock_db.execute.side_effect = [
        mock_agents_res,
        mock_spans_res,
        mock_alerts_res,
    ]

    app.dependency_overrides[get_db] = lambda: mock_db

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/agents/slos")
            assert resp.status_code == 200
            data = resp.json()
            assert len(data) == 1
            assert data[0]["agent_id"] == "agent_diag"
            assert data[0]["anomaly_count"] == 1
    finally:
        app.dependency_overrides.pop(get_db, None)


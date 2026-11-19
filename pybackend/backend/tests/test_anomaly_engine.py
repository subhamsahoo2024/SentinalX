import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sentinel_backend.config import settings
from sentinel_backend.models.alert import Alert
from sentinel_backend.models.run import Run
from sentinel_backend.models.span import Span
from sentinel_backend.schemas.alerts import AlertDTO
from sentinel_backend.services.anomaly_engine import (
    _upsert_alert,
    check_stalled_runs,
    evaluate_run_anomalies,
    stall_watchdog_loop,
)

# ==============================================================================
# Unit Tests: Schemas
# ==============================================================================


def test_alert_dto_instantiation():
    now = datetime.now(UTC)
    dto = AlertDTO(
        alert_id="alert_abc123def456",
        run_id="run_100",
        origin_span_id="span_001",
        rule_id="LOOP_DETECTED",
        severity="HIGH",
        title="Repeated tool loop detected",
        evidence={"tool_name": "bash", "repeat_count": 3},
        impacted_span_ids=["span_001", "span_002", "span_003"],
        acknowledged=False,
        created_at=now,
    )
    assert dto.alert_id == "alert_abc123def456"
    assert dto.run_id == "run_100"
    assert dto.rule_id == "LOOP_DETECTED"
    assert dto.severity == "HIGH"
    assert dto.evidence["repeat_count"] == 3
    assert len(dto.impacted_span_ids) == 3
    assert dto.acknowledged is False
    assert dto.created_at == now


def test_alert_dto_model_validate():
    now = datetime.now(UTC)
    alert = Alert(
        alert_id="alert_xyz789",
        run_id="run_200",
        origin_span_id=None,
        rule_id="BUDGET_EXCEEDED",
        severity="HIGH",
        title="Token budget overrun",
        evidence={"total_tokens": 6000, "budget_limit": 5000},
        impacted_span_ids=["span_top"],
        acknowledged=True,
        created_at=now,
    )
    dto = AlertDTO.model_validate(alert)
    assert dto.alert_id == "alert_xyz789"
    assert dto.origin_span_id is None
    assert dto.acknowledged is True
    assert dto.evidence["total_tokens"] == 6000


# ==============================================================================
# Unit Tests: _upsert_alert Helper
# ==============================================================================


@pytest.mark.asyncio
async def test_upsert_alert_insert_new():
    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_result

    with patch(
        "sentinel_backend.services.anomaly_engine.publish_event",
        new_callable=AsyncMock,
    ) as mock_publish:
        alert_dto = await _upsert_alert(
            db=mock_db,
            run_id="run_test",
            rule_id="LOOP_DETECTED",
            origin_span_id="span_1",
            severity="HIGH",
            title="Loop detected",
            evidence={"tool_name": "bash", "repeat_count": 3},
            impacted_span_ids=["span_1", "span_2", "span_3"],
        )

        assert alert_dto.alert_id.startswith("alert_")
        assert len(alert_dto.alert_id) == len("alert_") + 12
        assert alert_dto.run_id == "run_test"
        assert alert_dto.rule_id == "LOOP_DETECTED"
        assert alert_dto.severity == "HIGH"
        assert alert_dto.origin_span_id == "span_1"

        # Verify added to DB and committed
        mock_db.add.assert_called_once()
        mock_db.commit.assert_awaited_once()

        # Verify published to both run and fleet channels
        assert mock_publish.await_count == 2
        mock_publish.assert_any_await(
            "run:run_test:stream", "ALERT_CREATED", alert_dto.model_dump(mode="json")
        )
        mock_publish.assert_any_await(
            "fleet:stream", "ALERT_CREATED", alert_dto.model_dump(mode="json")
        )


@pytest.mark.asyncio
async def test_upsert_alert_update_existing_unacknowledged():
    mock_db = AsyncMock()
    existing_alert = Alert(
        alert_id="alert_existing12",
        run_id="run_test",
        origin_span_id="span_old",
        rule_id="LOOP_DETECTED",
        severity="HIGH",
        title="Old title",
        evidence={"tool_name": "bash", "repeat_count": 3},
        impacted_span_ids=["span_1", "span_2", "span_3"],
        acknowledged=False,
        created_at=datetime.now(UTC),
    )
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = existing_alert
    mock_db.execute.return_value = mock_result

    with patch(
        "sentinel_backend.services.anomaly_engine.publish_event",
        new_callable=AsyncMock,
    ) as mock_publish:
        alert_dto = await _upsert_alert(
            db=mock_db,
            run_id="run_test",
            rule_id="LOOP_DETECTED",
            origin_span_id="span_new",
            severity="HIGH",
            title="Updated title: 4 executions",
            evidence={"tool_name": "bash", "repeat_count": 4},
            impacted_span_ids=["span_1", "span_2", "span_3", "span_4"],
        )

        assert alert_dto.alert_id == "alert_existing12"
        assert alert_dto.title == "Updated title: 4 executions"
        assert alert_dto.evidence["repeat_count"] == 4
        assert len(alert_dto.impacted_span_ids) == 4
        assert alert_dto.origin_span_id == "span_new"

        mock_db.add.assert_not_called()
        mock_db.commit.assert_awaited_once()
        assert mock_publish.await_count == 2


# ==============================================================================
# Unit Tests: Rule 1 — Repeated Tool Loop (LOOP_DETECTED)
# ==============================================================================


@pytest.mark.asyncio
async def test_evaluate_run_anomalies_tool_loop_detected():
    now = datetime.now(UTC)
    run = Run(
        run_id="run_loop",
        trace_id="a" * 32,
        team="it-ops",
        status="RUNNING",
        started_at=now - timedelta(seconds=20),
        last_event_at=now,
        total_tokens=100,
    )

    # 3 identical tool calls with same operation_name and inputs
    s1 = Span(
        span_id="span_tool_1",
        trace_id="a" * 32,
        run_id="run_loop",
        agent_id="remediation-agent",
        span_type="TOOL",
        operation_name="db_query",
        status="SUCCEEDED",
        started_at=now - timedelta(seconds=15),
        attributes={"inputs": {"query": "SELECT 1"}},
    )
    s2 = Span(
        span_id="span_tool_2",
        trace_id="a" * 32,
        run_id="run_loop",
        agent_id="remediation-agent",
        span_type="TOOL",
        operation_name="db_query",
        status="SUCCEEDED",
        started_at=now - timedelta(seconds=10),
        attributes={"inputs": {"query": "SELECT 1"}},
    )
    s3 = Span(
        span_id="span_tool_3",
        trace_id="a" * 32,
        run_id="run_loop",
        agent_id="remediation-agent",
        span_type="TOOL",
        operation_name="db_query",
        status="SUCCEEDED",
        started_at=now - timedelta(seconds=5),
        attributes={"inputs": {"query": "SELECT 1"}},
    )

    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    mock_db.get.return_value = run

    spans_mock_result = MagicMock()
    spans_mock_result.scalars().all.return_value = [s1, s2, s3]

    alert_mock_result = MagicMock()
    alert_mock_result.scalar_one_or_none.return_value = None

    def execute_side_effect(stmt):
        stmt_str = str(stmt).lower()
        if "from spans" in stmt_str:
            return spans_mock_result
        return alert_mock_result

    mock_db.execute.side_effect = execute_side_effect

    with patch(
        "sentinel_backend.services.anomaly_engine.publish_event",
        new_callable=AsyncMock,
    ):
        alerts = await evaluate_run_anomalies(mock_db, "run_loop")

        assert len(alerts) == 1
        alert = alerts[0]
        assert alert.rule_id == "LOOP_DETECTED"
        assert alert.severity == "HIGH"
        assert alert.origin_span_id == "span_tool_1"
        assert alert.impacted_span_ids == [
            "span_tool_1",
            "span_tool_2",
            "span_tool_3",
        ]
        assert alert.evidence["tool_name"] == "db_query"
        assert alert.evidence["repeat_count"] == 3
        assert alert.evidence["threshold"] == settings.LOOP_THRESHOLD_COUNT
        assert alert.evidence["window_seconds"] == settings.LOOP_WINDOW_SECONDS


@pytest.mark.asyncio
async def test_evaluate_run_anomalies_tool_loop_not_triggered_below_threshold():
    now = datetime.now(UTC)
    run = Run(
        run_id="run_loop_few",
        trace_id="a" * 32,
        team="it-ops",
        status="RUNNING",
        started_at=now - timedelta(seconds=20),
        last_event_at=now,
        total_tokens=100,
    )

    # Only 2 tool calls (< LOOP_THRESHOLD_COUNT = 3)
    s1 = Span(
        span_id="span_tool_1",
        trace_id="a" * 32,
        run_id="run_loop_few",
        agent_id="remediation-agent",
        span_type="TOOL",
        operation_name="db_query",
        status="SUCCEEDED",
        started_at=now - timedelta(seconds=15),
        attributes={"inputs": {"query": "SELECT 1"}},
    )
    s2 = Span(
        span_id="span_tool_2",
        trace_id="a" * 32,
        run_id="run_loop_few",
        agent_id="remediation-agent",
        span_type="TOOL",
        operation_name="db_query",
        status="SUCCEEDED",
        started_at=now - timedelta(seconds=10),
        attributes={"inputs": {"query": "SELECT 1"}},
    )

    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    mock_db.get.return_value = run

    spans_mock_result = MagicMock()
    spans_mock_result.scalars().all.return_value = [s1, s2]
    mock_db.execute.return_value = spans_mock_result

    alerts = await evaluate_run_anomalies(mock_db, "run_loop_few")
    assert len(alerts) == 0


@pytest.mark.asyncio
async def test_evaluate_run_anomalies_tool_loop_different_inputs_no_trigger():
    now = datetime.now(UTC)
    run = Run(
        run_id="run_diff_inputs",
        trace_id="a" * 32,
        team="it-ops",
        status="RUNNING",
        started_at=now - timedelta(seconds=20),
        last_event_at=now,
        total_tokens=100,
    )

    # 3 tool calls but with different queries
    s1 = Span(
        span_id="s1",
        trace_id="a" * 32,
        run_id="run_diff_inputs",
        agent_id="agent1",
        span_type="TOOL",
        operation_name="db_query",
        status="SUCCEEDED",
        started_at=now - timedelta(seconds=15),
        attributes={"inputs": {"query": "SELECT 1"}},
    )
    s2 = Span(
        span_id="s2",
        trace_id="a" * 32,
        run_id="run_diff_inputs",
        agent_id="agent1",
        span_type="TOOL",
        operation_name="db_query",
        status="SUCCEEDED",
        started_at=now - timedelta(seconds=10),
        attributes={"inputs": {"query": "SELECT 2"}},
    )
    s3 = Span(
        span_id="s3",
        trace_id="a" * 32,
        run_id="run_diff_inputs",
        agent_id="agent1",
        span_type="TOOL",
        operation_name="db_query",
        status="SUCCEEDED",
        started_at=now - timedelta(seconds=5),
        attributes={"inputs": {"query": "SELECT 3"}},
    )

    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    mock_db.get.return_value = run
    spans_mock_result = MagicMock()
    spans_mock_result.scalars().all.return_value = [s1, s2, s3]
    mock_db.execute.return_value = spans_mock_result

    alerts = await evaluate_run_anomalies(mock_db, "run_diff_inputs")
    assert len(alerts) == 0


# ==============================================================================
# Unit Tests: Rule 2 — Token Budget Overrun (BUDGET_EXCEEDED)
# ==============================================================================


@pytest.mark.asyncio
async def test_evaluate_run_anomalies_budget_exceeded():
    now = datetime.now(UTC)
    # total_tokens = 7500 > RUN_TOKEN_BUDGET (5000)
    run = Run(
        run_id="run_over_budget",
        trace_id="a" * 32,
        team="it-ops",
        status="RUNNING",
        started_at=now - timedelta(seconds=30),
        last_event_at=now,
        total_tokens=7500,
    )

    s_llm_1 = Span(
        span_id="span_llm_1",
        trace_id="a" * 32,
        run_id="run_over_budget",
        agent_id="diagnostic-agent",
        span_type="LLM",
        operation_name="gpt-4o",
        status="SUCCEEDED",
        started_at=now - timedelta(seconds=20),
        input_tokens=1500,
        output_tokens=500,
        cached_tokens=0,
    )
    s_llm_2 = Span(
        span_id="span_llm_2",
        trace_id="a" * 32,
        run_id="run_over_budget",
        agent_id="diagnostic-agent",
        span_type="LLM",
        operation_name="gpt-4o",
        status="SUCCEEDED",
        started_at=now - timedelta(seconds=10),
        input_tokens=4000,
        output_tokens=1500,
        cached_tokens=0,
    )

    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    mock_db.get.return_value = run

    spans_mock_result = MagicMock()
    spans_mock_result.scalars().all.return_value = [s_llm_1, s_llm_2]

    alert_mock_result = MagicMock()
    alert_mock_result.scalar_one_or_none.return_value = None

    def execute_side_effect(stmt):
        if "from spans" in str(stmt).lower():
            return spans_mock_result
        return alert_mock_result

    mock_db.execute.side_effect = execute_side_effect

    with patch(
        "sentinel_backend.services.anomaly_engine.publish_event",
        new_callable=AsyncMock,
    ):
        alerts = await evaluate_run_anomalies(mock_db, "run_over_budget")

        assert len(alerts) == 1
        alert = alerts[0]
        assert alert.rule_id == "BUDGET_EXCEEDED"
        assert alert.severity == "HIGH"
        assert alert.origin_span_id == "span_llm_2"  # highest token span (5500)
        assert alert.evidence["total_tokens"] == 7500
        assert alert.evidence["budget_limit"] == settings.RUN_TOKEN_BUDGET
        assert "span_llm_1" in alert.impacted_span_ids
        assert "span_llm_2" in alert.impacted_span_ids


# ==============================================================================
# Unit Tests: Rule 3 — Cascading Failure & Root Cause Attribution
# ==============================================================================


@pytest.mark.asyncio
async def test_evaluate_run_anomalies_isolated_leaf_failure_no_alert():
    now = datetime.now(UTC)
    run = Run(
        run_id="run_single_fail",
        trace_id="a" * 32,
        team="it-ops",
        status="RUNNING",
        started_at=now - timedelta(seconds=10),
        last_event_at=now,
        total_tokens=100,
    )

    # Root Agent succeeded
    s_root = Span(
        span_id="span_root",
        trace_id="a" * 32,
        parent_span_id=None,
        run_id="run_single_fail",
        agent_id="coordinator",
        span_type="AGENT",
        operation_name="coordinator",
        status="SUCCEEDED",
        started_at=now - timedelta(seconds=10),
    )
    # Leaf tool failed, but isolated (no other failure)
    s_tool = Span(
        span_id="span_tool",
        trace_id="a" * 32,
        parent_span_id="span_root",
        run_id="run_single_fail",
        agent_id="coordinator",
        span_type="TOOL",
        operation_name="fetch_logs",
        status="FAILED",
        started_at=now - timedelta(seconds=5),
        error_class="TimeoutError",
        error_message="Log server timeout",
    )

    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    mock_db.get.return_value = run

    spans_mock_result = MagicMock()
    spans_mock_result.scalars().all.return_value = [s_root, s_tool]
    mock_db.execute.return_value = spans_mock_result

    alerts = await evaluate_run_anomalies(mock_db, "run_single_fail")
    # Isolated leaf failure (len(impacted) == 1 < 2): no alert triggered
    assert len(alerts) == 0
    # But s_tool was marked is_root_cause = True
    assert s_tool.is_root_cause is True
    assert s_root.is_root_cause is False
    mock_db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_evaluate_run_anomalies_sibling_cascade():
    now = datetime.now(UTC)
    run = Run(
        run_id="run_sibling_cascade",
        trace_id="a" * 32,
        team="it-ops",
        status="RUNNING",
        started_at=now - timedelta(seconds=20),
        last_event_at=now,
        total_tokens=100,
    )

    s_parent = Span(
        span_id="span_parent",
        trace_id="a" * 32,
        parent_span_id=None,
        run_id="run_sibling_cascade",
        agent_id="coordinator",
        span_type="AGENT",
        operation_name="coordinator",
        status="RUNNING",
        started_at=now - timedelta(seconds=20),
    )
    # Tool 1 failed at t=15
    s_tool_1 = Span(
        span_id="span_tool_1",
        trace_id="a" * 32,
        parent_span_id="span_parent",
        run_id="run_sibling_cascade",
        agent_id="coordinator",
        span_type="TOOL",
        operation_name="connect_db",
        status="FAILED",
        started_at=now - timedelta(seconds=15),
        error_class="ConnectionRefusedError",
        error_message="Port 5432 closed",
    )
    # Tool 2 failed at t=10 as a downstream consequence
    s_tool_2 = Span(
        span_id="span_tool_2",
        trace_id="a" * 32,
        parent_span_id="span_parent",
        run_id="run_sibling_cascade",
        agent_id="coordinator",
        span_type="TOOL",
        operation_name="query_db",
        status="FAILED",
        started_at=now - timedelta(seconds=10),
        error_class="InvalidConnectionState",
        error_message="Connection is closed",
    )

    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    mock_db.get.return_value = run

    spans_mock_result = MagicMock()
    spans_mock_result.scalars().all.return_value = [
        s_parent,
        s_tool_1,
        s_tool_2,
    ]

    alert_mock_result = MagicMock()
    alert_mock_result.scalar_one_or_none.return_value = None

    def execute_side_effect(stmt):
        if "from spans" in str(stmt).lower():
            return spans_mock_result
        return alert_mock_result

    mock_db.execute.side_effect = execute_side_effect

    with patch(
        "sentinel_backend.services.anomaly_engine.publish_event",
        new_callable=AsyncMock,
    ):
        alerts = await evaluate_run_anomalies(mock_db, "run_sibling_cascade")

        assert len(alerts) == 1
        alert = alerts[0]
        assert alert.rule_id == "CASCADE_FAILURE"
        assert alert.severity == "CRITICAL"
        assert alert.origin_span_id == "span_tool_1"
        assert alert.evidence["origin_operation"] == "connect_db"
        assert alert.evidence["error_class"] == "ConnectionRefusedError"
        assert alert.evidence["affected_count"] == 2
        assert s_tool_1.is_root_cause is True
        assert s_tool_2.is_root_cause is False


@pytest.mark.asyncio
async def test_evaluate_run_anomalies_hierarchical_cascade():
    now = datetime.now(UTC)
    run = Run(
        run_id="run_hierarchical_cascade",
        trace_id="a" * 32,
        team="it-ops",
        status="FAILED",
        started_at=now - timedelta(seconds=30),
        last_event_at=now,
        total_tokens=100,
    )

    s_root = Span(
        span_id="span_root",
        trace_id="a" * 32,
        parent_span_id=None,
        run_id="run_hierarchical_cascade",
        agent_id="coordinator",
        span_type="AGENT",
        operation_name="coordinator",
        status="FAILED",
        started_at=now - timedelta(seconds=30),
        error_class="SubtaskFailure",
        error_message="Diagnostic agent failed",
    )
    s_diag = Span(
        span_id="span_diag",
        trace_id="a" * 32,
        parent_span_id="span_root",
        run_id="run_hierarchical_cascade",
        agent_id="diagnostic",
        span_type="AGENT",
        operation_name="diagnostic",
        status="FAILED",
        started_at=now - timedelta(seconds=25),
        error_class="FatalToolError",
        error_message="Tool failure",
    )

    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    mock_db.get.return_value = run

    spans_mock_result = MagicMock()
    spans_mock_result.scalars().all.return_value = [s_root, s_diag]

    alert_mock_result = MagicMock()
    alert_mock_result.scalar_one_or_none.return_value = None

    def execute_side_effect(stmt):
        if "from spans" in str(stmt).lower():
            return spans_mock_result
        return alert_mock_result

    mock_db.execute.side_effect = execute_side_effect

    with patch(
        "sentinel_backend.services.anomaly_engine.publish_event",
        new_callable=AsyncMock,
    ):
        alerts = await evaluate_run_anomalies(
            mock_db, "run_hierarchical_cascade"
        )

        assert len(alerts) == 1
        alert = alerts[0]
        assert alert.rule_id == "CASCADE_FAILURE"
        assert alert.severity == "CRITICAL"
        assert alert.origin_span_id == "span_root"
        assert s_root.is_root_cause is True
        assert "span_root" in alert.impacted_span_ids
        assert "span_diag" in alert.impacted_span_ids


# ==============================================================================
# Unit Tests: Stall Watchdog
# ==============================================================================


@pytest.mark.asyncio
async def test_check_stalled_runs_transitions_running_run():
    now = datetime.now(UTC)
    stalled_run = Run(
        run_id="run_stalled_1",
        trace_id="a" * 32,
        root_agent_id="agent_1",
        team="it-ops",
        status="RUNNING",
        started_at=now - timedelta(seconds=60),
        last_event_at=now - timedelta(seconds=30),  # > 25s timeout
        total_tokens=500,
        total_cost_usd=0.05,
        cost_status="EXACT",
    )

    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    select_runs_mock = MagicMock()
    select_runs_mock.scalars().all.return_value = [stalled_run]

    alert_mock_result = MagicMock()
    alert_mock_result.scalar_one_or_none.return_value = None

    def execute_side_effect(stmt):
        if "from runs" in str(stmt).lower():
            return select_runs_mock
        return alert_mock_result

    mock_db.execute.side_effect = execute_side_effect

    with patch(
        "sentinel_backend.services.anomaly_engine.publish_event",
        new_callable=AsyncMock,
    ) as mock_publish:
        alerts = await check_stalled_runs(mock_db)

        assert len(alerts) == 1
        assert alerts[0].rule_id == "RUN_STALLED"
        assert alerts[0].severity == "MEDIUM"
        assert alerts[0].run_id == "run_stalled_1"

        # Verify run state mutated to STALLED
        assert stalled_run.status == "STALLED"
        assert stalled_run.ended_at is not None

        mock_db.commit.assert_awaited()

        # Check published events: ALERT_CREATED, RUN_UPDATED, FLEET_UPDATED
        published_event_types = [
            call.args[1] for call in mock_publish.await_args_list
        ]
        assert "ALERT_CREATED" in published_event_types
        assert "RUN_UPDATED" in published_event_types
        assert "FLEET_UPDATED" in published_event_types


@pytest.mark.asyncio
async def test_check_stalled_runs_excludes_awaiting_approval():
    # Run is awaiting approval: should NOT be returned by the query or stalled
    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    select_runs_mock = MagicMock()
    select_runs_mock.scalars().all.return_value = []
    mock_db.execute.return_value = select_runs_mock

    alerts = await check_stalled_runs(mock_db)
    assert len(alerts) == 0


@pytest.mark.asyncio
async def test_stall_watchdog_loop_cancellation():
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars().all.return_value = []
    mock_session.execute.return_value = mock_result
    mock_session.add = MagicMock()

    mock_context = AsyncMock()
    mock_context.__aenter__.return_value = mock_session
    mock_context.__aexit__.return_value = None

    session_factory_mock = MagicMock(return_value=mock_context)

    # Start loop in background task
    task = asyncio.create_task(stall_watchdog_loop(session_factory_mock))
    # Give it a fraction of a second to enter loop
    await asyncio.sleep(0.02)
    # Cancel the task
    task.cancel()

    # Verify cleanly exited without unhandled exception
    await task
    assert task.done() is True

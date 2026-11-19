from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sentinel_backend.db.session import get_db
from sentinel_backend.main import app
from sentinel_backend.models.alert import Alert
from sentinel_backend.models.run import Run
from sentinel_backend.services.ingestion import ingest_telemetry_batch
from sentinel_sdk.schema import (
    CanonicalEventV1,
    SpanStatus,
    SpanType,
)

# ==============================================================================
# API Tests: Alerts Router
# ==============================================================================


@pytest.mark.asyncio
async def test_get_alerts_endpoint():
    now = datetime.now(UTC)
    alert1 = Alert(
        alert_id="alert_1",
        run_id="run_100",
        origin_span_id="span_1",
        rule_id="LOOP_DETECTED",
        severity="HIGH",
        title="Loop detected",
        evidence={"tool_name": "bash", "repeat_count": 3},
        impacted_span_ids=["span_1"],
        acknowledged=False,
        created_at=now,
    )
    alert2 = Alert(
        alert_id="alert_2",
        run_id="run_200",
        origin_span_id="span_2",
        rule_id="BUDGET_EXCEEDED",
        severity="HIGH",
        title="Budget exceeded",
        evidence={"total_tokens": 6000},
        impacted_span_ids=["span_2"],
        acknowledged=True,
        created_at=now,
    )

    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars().all.return_value = [alert1, alert2]
    mock_db.execute.return_value = mock_result

    app.dependency_overrides[get_db] = lambda: mock_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/alerts")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert data[0]["alert_id"] == "alert_1"
        assert data[0]["rule_id"] == "LOOP_DETECTED"
        assert data[1]["alert_id"] == "alert_2"
        assert data[1]["acknowledged"] is True

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_get_alerts_filtering():
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars().all.return_value = []
    mock_db.execute.return_value = mock_result

    app.dependency_overrides[get_db] = lambda: mock_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/api/alerts?run_id=run_100&acknowledged=false&limit=10"
        )
        assert response.status_code == 200
        assert response.json() == []

        # Verify db.execute received query with filters
        mock_db.execute.assert_called_once()
        stmt = mock_db.execute.call_args[0][0]
        stmt_sql = str(stmt).lower()
        assert "where" in stmt_sql
        assert "limit" in stmt_sql

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_patch_alert_ack_success():
    now = datetime.now(UTC)
    alert = Alert(
        alert_id="alert_to_ack",
        run_id="run_100",
        origin_span_id="span_1",
        rule_id="LOOP_DETECTED",
        severity="HIGH",
        title="Loop detected",
        evidence={"tool_name": "bash", "repeat_count": 3},
        impacted_span_ids=["span_1"],
        acknowledged=False,
        created_at=now,
    )

    mock_db = AsyncMock()
    mock_db.get.return_value = alert

    app.dependency_overrides[get_db] = lambda: mock_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.patch("/api/alerts/alert_to_ack/ack")
        assert response.status_code == 200
        data = response.json()
        assert data["alert_id"] == "alert_to_ack"
        assert data["acknowledged"] is True
        assert alert.acknowledged is True
        mock_db.commit.assert_awaited_once()

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_patch_alert_ack_404_not_found():
    mock_db = AsyncMock()
    mock_db.get.return_value = None

    app.dependency_overrides[get_db] = lambda: mock_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.patch("/api/alerts/nonexistent_alert/ack")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    app.dependency_overrides.clear()


# ==============================================================================
# Integration Wiring: Ingestion Calls Anomaly Engine
# ==============================================================================


@pytest.mark.asyncio
async def test_ingest_telemetry_batch_wires_anomaly_engine():
    now = datetime.now(UTC)
    event = CanonicalEventV1(
        event_id="evt_1",
        trace_id="a" * 32,
        span_id="span_1",
        run_id="run_ingest_test",
        agent_id="test_agent",
        span_type=SpanType.AGENT,
        operation_name="coordinator",
        status=SpanStatus.RUNNING,
        started_at=now,
    )

    mock_db = AsyncMock()
    mock_db.add = MagicMock()

    # Mock execute for agent upsert, run upsert, span upsert, and token recomputation
    tokens_mock = MagicMock()
    tokens_mock.one.return_value = (100, 0.05)
    run_select_mock = MagicMock()
    mock_run = Run(
        run_id="run_ingest_test",
        trace_id="a" * 32,
        root_agent_id="test_agent",
        team="default",
        status="RUNNING",
        started_at=now,
        last_event_at=now,
        total_tokens=100,
        total_cost_usd=0.05,
        cost_status="EXACT",
    )
    run_select_mock.scalar_one_or_none.return_value = mock_run

    def execute_side_effect(stmt):
        stmt_str = str(stmt).lower()
        if "sum" in stmt_str:
            return tokens_mock
        if "from runs" in stmt_str:
            return run_select_mock
        return MagicMock()

    mock_db.execute.side_effect = execute_side_effect

    with patch(
        "sentinel_backend.services.ingestion.evaluate_run_anomalies",
        new_callable=AsyncMock,
    ) as mock_eval_anomalies, patch(
        "sentinel_backend.services.ingestion.publish_event",
        new_callable=AsyncMock,
    ):
        result = await ingest_telemetry_batch(mock_db, [event])

        assert result["accepted"] == 1
        assert result["run_ids"] == ["run_ingest_test"]

        # Verify evaluate_run_anomalies was called with db and run_id
        mock_eval_anomalies.assert_awaited_once_with(mock_db, "run_ingest_test")
        # Verify db was committed
        mock_db.commit.assert_awaited()

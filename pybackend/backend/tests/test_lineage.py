from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
from sentinel_backend.api.deps import ActorContext, get_current_actor
from sentinel_backend.api.runs import router
from sentinel_backend.db.session import get_db
from sentinel_backend.models.run import Run
from sentinel_backend.models.span import Span
from sentinel_backend.schemas.telemetry import (
    LineageGraphDTO,
    SpanDTO,
)
from sentinel_backend.services.lineage_builder import (
    build_run_lineage,
    get_run_events,
)


@pytest.mark.asyncio
async def test_build_run_lineage_404_missing_run():
    mock_db = AsyncMock()
    mock_db.get.return_value = None

    with pytest.raises(HTTPException) as exc_info:
        await build_run_lineage(mock_db, "non_existent_run")

    assert exc_info.value.status_code == 404
    assert "not found" in exc_info.value.detail


@pytest.mark.asyncio
async def test_build_run_lineage_graph_structure():
    now = datetime.now(UTC)
    t1 = now
    t2 = now + timedelta(milliseconds=250)
    t3 = now + timedelta(milliseconds=500)

    run = Run(
        run_id="run_test_123",
        trace_id="a" * 32,
        team="it-ops",
        status="RUNNING",
        started_at=t1,
        last_event_at=t3,
    )

    # Root span: coordinator
    s_root = Span(
        span_id="span_root",
        trace_id="a" * 32,
        parent_span_id=None,
        run_id="run_test_123",
        agent_id="coordinator-agent",
        attempt_number=1,
        span_type="AGENT",
        operation_name="coordinator",
        status="SUCCEEDED",
        started_at=t1,
        ended_at=t3,
        attributes={"inputs": {"task": "fix"}},
    )

    # Child 1: tool call attempt 1 (failed)
    s_tool_1 = Span(
        span_id="span_tool_att1",
        trace_id="a" * 32,
        parent_span_id="span_root",
        run_id="run_test_123",
        agent_id="tool-agent",
        attempt_number=1,
        span_type="TOOL",
        operation_name="restart_service",
        status="FAILED",
        started_at=t1,
        ended_at=t2,
        error_class="TimeoutError",
        error_message="Worker timeout",
        attributes={"inputs": {"service": "db"}},
    )

    # Child 2: repeated tool call attempt 2 (succeeded)
    s_tool_2 = Span(
        span_id="span_tool_att2",
        trace_id="a" * 32,
        parent_span_id="span_root",
        run_id="run_test_123",
        agent_id="tool-agent",
        attempt_number=2,
        span_type="TOOL",
        operation_name="restart_service",
        status="SUCCEEDED",
        started_at=t2,
        ended_at=t3,
        attributes={"inputs": {"service": "db"}},
    )

    # Child 3: Orphan span whose parent is missing from run's span set
    s_orphan = Span(
        span_id="span_orphan",
        trace_id="a" * 32,
        parent_span_id="span_missing_parent",
        run_id="run_test_123",
        agent_id="external-agent",
        attempt_number=1,
        span_type="LLM",
        operation_name="evaluate",
        status="SUCCEEDED",
        started_at=t2,
        ended_at=t3,
    )

    mock_db = AsyncMock()
    mock_db.get.return_value = run

    mock_res = MagicMock()
    mock_res.scalars.return_value.all.return_value = [
        s_root,
        s_tool_1,
        s_tool_2,
        s_orphan,
    ]
    mock_db.execute.return_value = mock_res

    graph: LineageGraphDTO = await build_run_lineage(mock_db, "run_test_123")

    assert graph.run_id == "run_test_123"
    assert graph.trace_id == "a" * 32
    assert graph.status == "RUNNING"
    assert len(graph.nodes) == 4

    # Every node is keyed strictly by span.span_id
    node_ids = [n.id for n in graph.nodes]
    assert node_ids == [
        "span_root",
        "span_tool_att1",
        "span_tool_att2",
        "span_orphan",
    ]

    # Attempt numbers preserved
    assert graph.nodes[1].attempt_number == 1
    assert graph.nodes[2].attempt_number == 2
    assert graph.nodes[1].operation_name == "restart_service"
    assert graph.nodes[2].operation_name == "restart_service"

    # Durations computed in ms
    assert graph.nodes[0].duration_ms == pytest.approx(500.0, rel=1e-2)
    assert graph.nodes[1].duration_ms == pytest.approx(250.0, rel=1e-2)

    # Edges: only 2 valid edges (s_root -> s_tool_1, s_root -> s_tool_2)
    assert len(graph.edges) == 2
    edge_failed = next(e for e in graph.edges if e.target == "span_tool_att1")
    assert edge_failed.id == "span_root->span_tool_att1"
    assert edge_failed.source == "span_root"
    assert edge_failed.is_failed_path is True

    edge_ok = next(e for e in graph.edges if e.target == "span_tool_att2")
    assert edge_ok.id == "span_root->span_tool_att2"
    assert edge_ok.source == "span_root"
    assert edge_ok.is_failed_path is False

    # Orphan spans recorded without crashing
    assert graph.orphan_span_ids == ["span_orphan"]


@pytest.mark.asyncio
async def test_get_run_events_chronological():
    now = datetime.now(UTC)
    run = Run(
        run_id="run_abc",
        trace_id="b" * 32,
        team="it-ops",
        status="SUCCEEDED",
        started_at=now,
        last_event_at=now,
    )
    s1 = Span(
        span_id="s1",
        trace_id="b" * 32,
        parent_span_id=None,
        run_id="run_abc",
        agent_id="a1",
        attempt_number=1,
        span_type="AGENT",
        operation_name="start",
        status="SUCCEEDED",
        started_at=now,
        ended_at=now + timedelta(seconds=1),
    )
    s2 = Span(
        span_id="s2",
        trace_id="b" * 32,
        parent_span_id="s1",
        run_id="run_abc",
        agent_id="a1",
        attempt_number=1,
        span_type="TOOL",
        operation_name="finish",
        status="SUCCEEDED",
        started_at=now + timedelta(seconds=2),
        ended_at=now + timedelta(seconds=3),
    )

    mock_db = AsyncMock()
    mock_db.get.return_value = run

    mock_res = MagicMock()
    mock_res.scalars.return_value.all.return_value = [s1, s2]
    mock_db.execute.return_value = mock_res

    events: list[SpanDTO] = await get_run_events(mock_db, "run_abc")
    assert len(events) == 2
    assert events[0].span_id == "s1"
    assert events[1].span_id == "s2"
    assert events[0].duration_ms == pytest.approx(1000.0, rel=1e-2)


@pytest.mark.asyncio
async def test_run_lineage_and_events_api_endpoints():
    from fastapi import FastAPI

    test_app = FastAPI()
    test_app.include_router(router)

    now = datetime.now(UTC)
    run = Run(
        run_id="run_api_test",
        trace_id="c" * 32,
        team="qa",
        status="RUNNING",
        started_at=now,
        last_event_at=now,
    )
    span = Span(
        span_id="span_1",
        trace_id="c" * 32,
        parent_span_id=None,
        run_id="run_api_test",
        agent_id="agent_1",
        attempt_number=1,
        span_type="AGENT",
        operation_name="op1",
        status="SUCCEEDED",
        started_at=now,
        ended_at=now + timedelta(seconds=1),
    )

    mock_db = AsyncMock()

    async def override_get_db():
        yield mock_db

    test_app.dependency_overrides[get_db] = override_get_db
    test_app.dependency_overrides[get_current_actor] = lambda: ActorContext(
        actor_id="qa-user",
        actor_role="operator",
        allowed_teams=["qa"],
        is_demo=False,
    )

    # Test 1: Successful lineage call
    mock_db.get.return_value = run
    mock_res = MagicMock()
    mock_res.scalars.return_value.all.return_value = [span]
    mock_db.execute.return_value = mock_res

    async with AsyncClient(
        transport=ASGITransport(app=test_app), base_url="http://test"
    ) as client:
        resp_lineage = await client.get("/api/runs/run_api_test/lineage")
        assert resp_lineage.status_code == 200
        data = resp_lineage.json()
        assert data["run_id"] == "run_api_test"
        assert len(data["nodes"]) == 1
        assert data["nodes"][0]["id"] == "span_1"

        # Test 2: Successful events call
        resp_events = await client.get("/api/runs/run_api_test/events")
        assert resp_events.status_code == 200
        ev_data = resp_events.json()
        assert len(ev_data) == 1
        assert ev_data[0]["span_id"] == "span_1"

        # Test 3: 404 for missing run
        mock_db.get.return_value = None
        resp_404_lineage = await client.get("/api/runs/missing_run/lineage")
        assert resp_404_lineage.status_code == 404

        resp_404_events = await client.get("/api/runs/missing_run/events")
        assert resp_404_events.status_code == 404

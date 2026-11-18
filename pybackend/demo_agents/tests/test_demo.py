from sentinel_demo.agents import (
    check_db_metrics,
    clear_stale_cache,
    fetch_service_logs,
    restart_worker_node,
    run_coordinator_agent,
)
from sentinel_demo.mock_llm import mock_llm_completion
from sentinel_sdk import CanonicalEventV1, SpanStatus, SpanType, get_exporter, start_run


def test_mock_llm_emits_traced_span():
    emitted: list[CanonicalEventV1] = []
    exporter = get_exporter()
    exporter.enqueue = lambda e: emitted.append(e)

    res = mock_llm_completion("Triage critical outage incident", latency_ms=10)
    assert "content" in res
    assert "usage" in res
    assert res["model"] == "gpt-4o"
    assert res["provider"] == "openai"

    assert len(emitted) == 2
    start_ev, end_ev = emitted
    assert start_ev.status == SpanStatus.RUNNING
    assert start_ev.span_type == SpanType.LLM
    assert end_ev.status == SpanStatus.SUCCEEDED
    assert end_ev.usage is not None
    assert end_ev.usage.input_tokens > 0
    assert end_ev.usage.output_tokens > 0


def test_tools_redaction_and_metrics():
    emitted: list[CanonicalEventV1] = []
    exporter = get_exporter()
    exporter.enqueue = lambda e: emitted.append(e)

    # 1. fetch_service_logs with sensitive token
    logs = fetch_service_logs("payment-service", api_token="sk-super-secret-key")
    assert logs["service"] == "payment-service"
    assert len(emitted) == 2
    assert emitted[0].span_type == SpanType.TOOL
    assert emitted[0].operation_name == "fetch_service_logs"
    assert emitted[0].attributes["inputs"]["api_token"] == "[REDACTED]"

    emitted.clear()

    # 2. check_db_metrics
    metrics = check_db_metrics("cluster-01")
    assert metrics["health_status"] == "DEGRADED"
    assert len(emitted) == 2
    assert emitted[0].operation_name == "check_db_metrics"

    emitted.clear()

    # 3. clear_stale_cache
    cache = clear_stale_cache("us-east-1")
    assert cache["status"] == "CACHE_CLEARED"
    assert len(emitted) == 2
    assert emitted[0].operation_name == "clear_stale_cache"

    emitted.clear()

    # 4. restart_worker_node
    restart = restart_worker_node("node-04")
    assert restart["restart_status"] == "RESTARTED"
    assert len(emitted) == 2
    assert emitted[0].operation_name == "restart_worker_node"


def test_coordinator_agent_hierarchy():
    emitted: list[CanonicalEventV1] = []
    exporter = get_exporter()
    exporter.enqueue = lambda e: emitted.append(e)

    with start_run(team="it-ops") as run_ctx:
        assert run_ctx.team == "it-ops"
        res = run_coordinator_agent(
            ticket_id="INC-1234",
            description="Database pool saturation",
        )
        assert res["status"] == "RESOLVED"
        assert res["ticket_id"] == "INC-1234"

    # There should be 10 operations executed:
    # 1. coordinator-agent (AGENT)
    # 2. coordinator mock_llm (LLM)
    # 3. diagnostic-agent (AGENT)
    # 4. diagnostic mock_llm (LLM)
    # 5. fetch_service_logs (TOOL)
    # 6. check_db_metrics (TOOL)
    # 7. remediation-agent (AGENT)
    # 8. remediation mock_llm (LLM)
    # 9. clear_stale_cache (TOOL)
    # 10. restart_worker_node (TOOL)
    # Total events: 10 start + 10 end = 20 events
    assert len(emitted) == 20

    # Map by span_id
    spans_by_id: dict[str, list[CanonicalEventV1]] = {}
    for ev in emitted:
        spans_by_id.setdefault(ev.span_id, []).append(ev)

    assert len(spans_by_id) == 10

    # Coordinator span is root (parent_span_id is None)
    coord_start = emitted[0]
    assert coord_start.operation_name == "run_coordinator_agent"
    assert coord_start.agent_id == "coordinator-agent"
    assert coord_start.parent_span_id is None
    coord_span_id = coord_start.span_id

    # Children of coordinator:
    # - triage LLM
    # - diagnostic agent
    # - remediation agent
    children_of_coord = [
        ev for ev in emitted
        if ev.parent_span_id == coord_span_id and ev.status == SpanStatus.RUNNING
    ]
    assert len(children_of_coord) == 3

    triage_llm_ev = children_of_coord[0]
    assert triage_llm_ev.span_type == SpanType.LLM

    diag_agent_ev = children_of_coord[1]
    assert diag_agent_ev.span_type == SpanType.AGENT
    assert diag_agent_ev.agent_id == "diagnostic-agent"

    remed_agent_ev = children_of_coord[2]
    assert remed_agent_ev.span_type == SpanType.AGENT
    assert remed_agent_ev.agent_id == "remediation-agent"

    # Children of diagnostic agent:
    children_of_diag = [
        ev for ev in emitted
        if ev.parent_span_id == diag_agent_ev.span_id and ev.status == SpanStatus.RUNNING
    ]
    assert len(children_of_diag) == 3
    assert children_of_diag[0].span_type == SpanType.LLM
    assert children_of_diag[1].operation_name == "fetch_service_logs"
    assert children_of_diag[1].attributes["inputs"]["api_token"] == "[REDACTED]"
    assert children_of_diag[2].operation_name == "check_db_metrics"

    # Children of remediation agent:
    children_of_remed = [
        ev for ev in emitted
        if ev.parent_span_id == remed_agent_ev.span_id and ev.status == SpanStatus.RUNNING
    ]
    assert len(children_of_remed) == 3
    assert children_of_remed[0].span_type == SpanType.LLM
    assert children_of_remed[1].operation_name == "clear_stale_cache"
    assert children_of_remed[2].operation_name == "restart_worker_node"

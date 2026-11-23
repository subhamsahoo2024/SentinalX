import time
from unittest.mock import MagicMock, patch

import pytest
from sentinel_demo.agents import run_slow_loop_agent
from sentinel_sdk import (
    BudgetCircuitBreakerError,
    RunCancelledError,
    SentinelExporter,
    SpanStatus,
    SpanType,
    configure_sentinel,
    start_run,
    trace_llm,
    trace_tool,
)
from sentinel_sdk.decorators import _CONTROL_CACHE, _check_runtime_control


@pytest.fixture
def mock_exporter():
    exporter = SentinelExporter(base_url="http://127.0.0.1:8000", api_key="test-key")
    exporter.enqueue = MagicMock()
    exporter.flush = MagicMock()
    configure_sentinel(base_url="http://127.0.0.1:8000", api_key="test-key")
    with patch("sentinel_sdk.decorators.get_exporter", return_value=exporter):
        yield exporter


@pytest.fixture(autouse=True)
def clear_control_cache():
    _CONTROL_CACHE.clear()
    yield
    _CONTROL_CACHE.clear()


# ==============================================================================
# 1. Helper & Caching Tests
# ==============================================================================
def test_check_runtime_control_caching_and_ttl():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"run_id": "run_cache_1", "cancelled": True, "blocked_reason": "BUDGET_EXCEEDED"}

    with patch("httpx.Client.get", return_value=mock_resp) as mock_get:
        # First call hits endpoint
        res1 = _check_runtime_control("run_cache_1")
        assert res1["cancelled"] is True
        assert res1["blocked_reason"] == "BUDGET_EXCEEDED"
        assert mock_get.call_count == 1

        # Second call within 0.25s hits in-memory cache
        res2 = _check_runtime_control("run_cache_1")
        assert res2["cancelled"] is True
        assert mock_get.call_count == 1

        # Wait out TTL
        time.sleep(0.3)
        res3 = _check_runtime_control("run_cache_1")
        assert res3["cancelled"] is True
        assert mock_get.call_count == 2


def test_check_runtime_control_fails_open_on_network_error():
    with patch("httpx.Client.get", side_effect=Exception("Connection refused")):
        res = _check_runtime_control("run_offline")
        assert res == {"cancelled": False, "blocked_reason": None}


def test_check_runtime_control_fails_open_on_missing_config():
    with patch("sentinel_sdk.decorators._resolve_sentinel_config", side_effect=ValueError("Missing env")):
        res = _check_runtime_control("run_no_cfg")
        assert res == {"cancelled": False, "blocked_reason": None}


# ==============================================================================
# 2. Kill-Switch (Cancellation) Gate Tests
# ==============================================================================
def test_trace_tool_sync_cancelled(mock_exporter):
    @trace_tool(tool_name="sample_sync_tool")
    def sample_sync_tool(x: int) -> int:
        return x * 2

    with (
        start_run(team="it-ops"),
        patch(
            "sentinel_sdk.decorators._check_runtime_control",
            return_value={"cancelled": True, "blocked_reason": None},
        ),
    ):
        with pytest.raises(RunCancelledError) as exc_info:
            sample_sync_tool(5)

        assert "Run aborted by operator kill-switch" in str(exc_info.value)
        assert mock_exporter.flush.called
        assert mock_exporter.enqueue.called

        enqueued_events = [c[0][0] for c in mock_exporter.enqueue.call_args_list]
        cancelled_events = [e for e in enqueued_events if e.status == SpanStatus.CANCELLED]
        assert len(cancelled_events) == 1
        assert cancelled_events[0].span_type == SpanType.TOOL
        assert cancelled_events[0].error.error_class == "RunCancelledError"


@pytest.mark.asyncio
async def test_trace_tool_async_cancelled(mock_exporter):
    @trace_tool(tool_name="sample_async_tool")
    async def sample_async_tool(msg: str) -> str:
        return f"echo: {msg}"

    with (
        start_run(team="it-ops"),
        patch(
            "sentinel_sdk.decorators._check_runtime_control",
            return_value={"cancelled": True, "blocked_reason": None},
        ),
    ):
        with pytest.raises(RunCancelledError) as exc_info:
            await sample_async_tool("hello")

        assert "Run aborted by operator kill-switch" in str(exc_info.value)
        assert mock_exporter.flush.called

        enqueued_events = [c[0][0] for c in mock_exporter.enqueue.call_args_list]
        cancelled_events = [e for e in enqueued_events if e.status == SpanStatus.CANCELLED]
        assert len(cancelled_events) == 1
        assert cancelled_events[0].span_type == SpanType.TOOL


# ==============================================================================
# 3. Budget Circuit-Breaker Gate Tests
# ==============================================================================
def test_trace_llm_sync_budget_circuit_breaker(mock_exporter):
    @trace_llm(provider="openai", model="gpt-4o")
    def sample_llm_call(prompt: str) -> dict[str, str]:
        return {"content": "ok"}

    with (
        start_run(team="it-ops"),
        patch(
            "sentinel_sdk.decorators._check_runtime_control",
            return_value={"cancelled": False, "blocked_reason": "BUDGET_EXCEEDED"},
        ),
    ):
        with pytest.raises(BudgetCircuitBreakerError) as exc_info:
            sample_llm_call("generate report")

        assert "Blocked by policy: BUDGET_EXCEEDED" in str(exc_info.value)
        assert mock_exporter.flush.called

        enqueued_events = [c[0][0] for c in mock_exporter.enqueue.call_args_list]
        blocked_events = [e for e in enqueued_events if e.status == SpanStatus.CANCELLED]
        assert len(blocked_events) == 1
        assert blocked_events[0].span_type == SpanType.LLM
        assert blocked_events[0].error.error_class == "BudgetCircuitBreakerError"


@pytest.mark.asyncio
async def test_trace_llm_async_budget_circuit_breaker(mock_exporter):
    @trace_llm(provider="anthropic", model="claude-3-7-sonnet")
    async def sample_async_llm_call(prompt: str) -> dict[str, str]:
        return {"content": "ok"}

    with (
        start_run(team="it-ops"),
        patch(
            "sentinel_sdk.decorators._check_runtime_control",
            return_value={"cancelled": False, "blocked_reason": "TOKEN_CEILING_REACHED"},
        ),
    ):
        with pytest.raises(BudgetCircuitBreakerError) as exc_info:
            await sample_async_llm_call("analyze")

        assert "Blocked by policy: TOKEN_CEILING_REACHED" in str(exc_info.value)
        assert mock_exporter.flush.called

        enqueued_events = [c[0][0] for c in mock_exporter.enqueue.call_args_list]
        blocked_events = [e for e in enqueued_events if e.status == SpanStatus.CANCELLED]
        assert len(blocked_events) == 1
        assert blocked_events[0].span_type == SpanType.LLM


def test_trace_tool_not_halted_by_llm_budget_circuit_breaker(mock_exporter):
    """Tool executions should not be blocked when only blocked_reason (for LLM) is set."""
    @trace_tool(tool_name="unaffected_tool")
    def unaffected_tool() -> str:
        return "tool_completed"

    with (
        start_run(team="it-ops"),
        patch(
            "sentinel_sdk.decorators._check_runtime_control",
            return_value={"cancelled": False, "blocked_reason": "BUDGET_EXCEEDED"},
        ),
    ):
        result = unaffected_tool()
        assert result == "tool_completed"


# ==============================================================================
# 4. Slow Loop Kill-Switch Demo Scenario Tests
# ==============================================================================
def test_slow_loop_scenario_kill_switch(mock_exporter):
    call_count = 0

    def mock_control_state(run_id: str):
        nonlocal call_count
        call_count += 1
        # Trigger cancellation on 2nd iteration
        if call_count >= 2:
            return {"cancelled": True, "blocked_reason": None}
        return {"cancelled": False, "blocked_reason": None}

    with (
        start_run(team="it-ops"),
        patch("time.sleep", return_value=None),  # Don't actually sleep during test
        patch("sentinel_sdk.decorators._check_runtime_control", side_effect=mock_control_state),
    ):
        with pytest.raises(RunCancelledError):
            run_slow_loop_agent(ticket_id="INC-TEST-1")

        assert call_count >= 2


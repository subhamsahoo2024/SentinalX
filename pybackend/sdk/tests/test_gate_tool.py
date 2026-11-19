from unittest.mock import MagicMock, patch

import pytest
from sentinel_sdk import (
    GovernanceRejectedError,
    GovernanceTimeoutError,
    SentinelExporter,
    SpanStatus,
    SpanType,
    configure_sentinel,
    gate_tool,
    start_run,
)


@pytest.fixture
def mock_exporter():
    exporter = SentinelExporter(base_url="http://127.0.0.1:8000", api_key="test-key")
    exporter.enqueue = MagicMock()
    exporter.flush = MagicMock()
    configure_sentinel(base_url="http://127.0.0.1:8000", api_key="test-key")
    with patch("sentinel_sdk.decorators.get_exporter", return_value=exporter):
        yield exporter


# ==============================================================================
# 1. Sync @gate_tool Tests
# ==============================================================================
def test_sync_gate_tool_approved(mock_exporter):
    executed = False

    @gate_tool(
        tool_name="restart_cluster",
        risk_level="CRITICAL",
        policy_reason="Impacts traffic",
        timeout_seconds=5,
    )
    def dummy_tool(cluster: str, secret_token: str = "supersecret") -> dict[str, str]:
        nonlocal executed
        executed = True
        return {"cluster": cluster, "status": "ok"}

    # Mock HTTP calls
    def mock_post(url, **kwargs):
        resp = MagicMock()
        resp.is_success = True
        resp.json.return_value = {"approval_id": "apr_12345", "status": "PENDING"}
        return resp

    def mock_get(url, **kwargs):
        resp = MagicMock()
        resp.is_success = True
        resp.json.return_value = {
            "approval_id": "apr_12345",
            "status": "APPROVED",
            "decided_by": "lead-approver",
            "comment": "all clear",
        }
        return resp

    with patch("httpx.Client.post", side_effect=mock_post), patch(
        "httpx.Client.get", side_effect=mock_get
    ), start_run(team="it-ops"):
        res = dummy_tool(cluster="prod-db", secret_token="my-token")

    assert executed is True
    assert res == {"cluster": "prod-db", "status": "ok"}

    # Verify emitted events
    enqueued_events = [call.args[0] for call in mock_exporter.enqueue.call_args_list]
    statuses = [e.status for e in enqueued_events]
    assert SpanStatus.AWAITING_APPROVAL in statuses
    assert SpanStatus.RUNNING in statuses
    assert SpanStatus.SUCCEEDED in statuses

    # Verify input arguments were redacted
    awaiting_event = next(e for e in enqueued_events if e.status == SpanStatus.AWAITING_APPROVAL)
    assert awaiting_event.attributes["inputs"]["secret_token"] == "[REDACTED]"
    assert awaiting_event.attributes["inputs"]["cluster"] == "prod-db"
    assert awaiting_event.span_type == SpanType.TOOL

    # Verify flush was called immediately
    assert mock_exporter.flush.called


def test_sync_gate_tool_rejected(mock_exporter):
    executed = False

    @gate_tool(
        tool_name="drop_table",
        risk_level="HIGH",
        policy_reason="Data loss risk",
        timeout_seconds=5,
    )
    def dummy_destructive_tool(table: str) -> None:
        nonlocal executed
        executed = True

    def mock_post(url, **kwargs):
        resp = MagicMock()
        resp.is_success = True
        resp.json.return_value = {"approval_id": "apr_reject_1", "status": "PENDING"}
        return resp

    def mock_get(url, **kwargs):
        resp = MagicMock()
        resp.is_success = True
        resp.json.return_value = {
            "approval_id": "apr_reject_1",
            "status": "REJECTED",
            "decided_by": "sec-ops",
            "comment": "Denied by security policy",
        }
        return resp

    with patch("httpx.Client.post", side_effect=mock_post), patch(
        "httpx.Client.get", side_effect=mock_get
    ), start_run(team="security"), pytest.raises(GovernanceRejectedError) as exc_info:
        dummy_destructive_tool(table="users")

    assert executed is False
    assert "Denied by security policy" in str(exc_info.value)

    enqueued_events = [call.args[0] for call in mock_exporter.enqueue.call_args_list]
    statuses = [e.status for e in enqueued_events]
    assert SpanStatus.AWAITING_APPROVAL in statuses
    assert SpanStatus.CANCELLED in statuses
    assert SpanStatus.RUNNING not in statuses
    assert SpanStatus.SUCCEEDED not in statuses


def test_sync_gate_tool_timeout(mock_exporter):
    executed = False

    @gate_tool(
        tool_name="reboot_host",
        risk_level="HIGH",
        policy_reason="Reboot host",
        timeout_seconds=1,
    )
    def dummy_tool(host: str) -> None:
        nonlocal executed
        executed = True

    def mock_post(url, **kwargs):
        resp = MagicMock()
        resp.is_success = True
        resp.json.return_value = {"approval_id": "apr_timeout_1", "status": "PENDING"}
        return resp

    def mock_get(url, **kwargs):
        # Continually returns PENDING
        resp = MagicMock()
        resp.is_success = True
        resp.json.return_value = {"approval_id": "apr_timeout_1", "status": "PENDING"}
        return resp

    with patch("httpx.Client.post", side_effect=mock_post), patch(
        "httpx.Client.get", side_effect=mock_get
    ), start_run(team="it-ops"), pytest.raises(GovernanceTimeoutError) as exc_info:
        dummy_tool(host="srv-01")

    assert executed is False
    assert "timed out after 1s" in str(exc_info.value)

    enqueued_events = [call.args[0] for call in mock_exporter.enqueue.call_args_list]
    statuses = [e.status for e in enqueued_events]
    assert SpanStatus.AWAITING_APPROVAL in statuses
    assert SpanStatus.TIMED_OUT in statuses


# ==============================================================================
# 2. Async @gate_tool Tests
# ==============================================================================
@pytest.mark.asyncio
async def test_async_gate_tool_approved(mock_exporter):
    executed = False

    @gate_tool(
        tool_name="async_failover",
        risk_level="CRITICAL",
        policy_reason="Database failover",
        timeout_seconds=5,
    )
    async def dummy_async_tool(cluster_id: str) -> str:
        nonlocal executed
        executed = True
        return f"failed_over_{cluster_id}"

    async def mock_async_post(url, **kwargs):
        resp = MagicMock()
        resp.is_success = True
        resp.json.return_value = {"approval_id": "apr_async_1", "status": "PENDING"}
        return resp

    async def mock_async_get(url, **kwargs):
        resp = MagicMock()
        resp.is_success = True
        resp.json.return_value = {
            "approval_id": "apr_async_1",
            "status": "APPROVED",
            "decided_by": "on-call",
            "comment": "Go ahead",
        }
        return resp

    with patch("httpx.AsyncClient.post", side_effect=mock_async_post), patch(
        "httpx.AsyncClient.get", side_effect=mock_async_get
    ), start_run(team="it-ops"):
        res = await dummy_async_tool(cluster_id="pg-prod-1")

    assert executed is True
    assert res == "failed_over_pg-prod-1"

    enqueued_events = [call.args[0] for call in mock_exporter.enqueue.call_args_list]
    statuses = [e.status for e in enqueued_events]
    assert SpanStatus.AWAITING_APPROVAL in statuses
    assert SpanStatus.RUNNING in statuses
    assert SpanStatus.SUCCEEDED in statuses


@pytest.mark.asyncio
async def test_async_gate_tool_rejected(mock_exporter):
    executed = False

    @gate_tool(
        tool_name="async_drop_partition",
        risk_level="CRITICAL",
        policy_reason="Data partition removal",
        timeout_seconds=5,
    )
    async def dummy_async_destructive(partition: str) -> None:
        nonlocal executed
        executed = True

    async def mock_async_post(url, **kwargs):
        resp = MagicMock()
        resp.is_success = True
        resp.json.return_value = {"approval_id": "apr_async_rej", "status": "PENDING"}
        return resp

    async def mock_async_get(url, **kwargs):
        resp = MagicMock()
        resp.is_success = True
        resp.json.return_value = {
            "approval_id": "apr_async_rej",
            "status": "REJECTED",
            "decided_by": "db-admin",
            "comment": "Partition contains active customer records",
        }
        return resp

    with patch("httpx.AsyncClient.post", side_effect=mock_async_post), patch(
        "httpx.AsyncClient.get", side_effect=mock_async_get
    ), start_run(team="data-eng"), pytest.raises(GovernanceRejectedError) as exc_info:
        await dummy_async_destructive(partition="p2026_11")

    assert executed is False
    assert "Partition contains active customer records" in str(exc_info.value)

    enqueued_events = [call.args[0] for call in mock_exporter.enqueue.call_args_list]
    statuses = [e.status for e in enqueued_events]
    assert SpanStatus.AWAITING_APPROVAL in statuses
    assert SpanStatus.CANCELLED in statuses

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
    ExportTraceServiceRequest,
)
from opentelemetry.proto.trace.v1.trace_pb2 import Status
from sentinel_backend.api.deps import IngestContext, verify_ingest_auth
from sentinel_backend.config import settings
from sentinel_backend.db.session import get_db
from sentinel_backend.main import app
from sentinel_backend.services.otlp_mapper import parse_otlp_request
from sentinel_sdk.schema import SpanStatus, SpanType

# ==============================================================================
# 1. Tests for otlp_mapper: parse_otlp_request with JSON payloads
# ==============================================================================


def test_parse_otlp_json_llm_chat():
    trace_id_hex = "4bf92f3577b34da6a3ce929d0e0e4736"
    span_id_hex = "00f067aa0ba902b7"
    parent_span_id_hex = "5fb397be34d23b0f"

    raw_json = {
        "resourceSpans": [
            {
                "resource": {
                    "attributes": [
                        {"key": "service.name", "value": {"stringValue": "finance-agent-service"}},
                        {"key": "deployment.environment", "value": {"stringValue": "production"}},
                    ]
                },
                "scopeSpans": [
                    {
                        "spans": [
                            {
                                "traceId": trace_id_hex,
                                "spanId": span_id_hex,
                                "parentSpanId": parent_span_id_hex,
                                "name": "openai_chat",
                                "startTimeUnixNano": "1700000000000000000",
                                "endTimeUnixNano": "1700000002000000000",
                                "status": {"code": 1},
                                "attributes": [
                                    {"key": "gen_ai.operation.name", "value": {"stringValue": "chat"}},
                                    {"key": "gen_ai.system", "value": {"stringValue": "openai"}},
                                    {"key": "gen_ai.request.model", "value": {"stringValue": "gpt-4o"}},
                                    {"key": "gen_ai.agent.id", "value": {"stringValue": "finance-agent"}},
                                    {"key": "gen_ai.usage.input_tokens", "value": {"intValue": "120"}},
                                    {"key": "gen_ai.usage.output_tokens", "value": {"intValue": "45"}},
                                    {"key": "user_api_key", "value": {"stringValue": "sk-secret-token"}},
                                ],
                            }
                        ]
                    }
                ],
            }
        ]
    }

    raw_bytes = json.dumps(raw_json).encode("utf-8")
    events = parse_otlp_request(raw_bytes, "application/json")

    assert len(events) == 1
    evt = events[0]

    assert evt.trace_id == trace_id_hex
    assert evt.run_id == f"run_otel_{trace_id_hex[:12]}"
    assert evt.span_id == f"otel_{span_id_hex}"
    assert evt.parent_span_id == f"otel_{parent_span_id_hex}"
    assert evt.agent_id == "finance-agent"
    assert evt.team == "production"
    assert evt.framework == "opentelemetry"
    assert evt.span_type == SpanType.LLM
    assert evt.operation_name == "gpt-4o"
    assert evt.status == SpanStatus.SUCCEEDED
    assert evt.started_at == datetime.fromtimestamp(1700000000, tz=UTC)
    assert evt.ended_at == datetime.fromtimestamp(1700000002, tz=UTC)

    assert evt.model is not None
    assert evt.model.provider == "openai"
    assert evt.model.name == "gpt-4o"

    assert evt.usage is not None
    assert evt.usage.input_tokens == 120
    assert evt.usage.output_tokens == 45

    # Check that sensitive attribute was redacted
    assert evt.attributes["user_api_key"] == "[REDACTED]"


def test_parse_otlp_json_tool_execution():
    raw_json = {
        "resourceSpans": [
            {
                "resource": {
                    "attributes": [
                        {"key": "service.name", "value": {"stringValue": "trading-bot"}},
                        {"key": "team", "value": {"stringValue": "quant-team"}},
                    ]
                },
                "scopeSpans": [
                    {
                        "spans": [
                            {
                                "traceId": "a1b2c3d4e5f60718293a4b5c6d7e8f90",
                                "spanId": "1122334455667788",
                                "name": "exec_order",
                                "startTimeUnixNano": "1700000005000000000",
                                "endTimeUnixNano": "1700000006000000000",
                                "attributes": [
                                    {"key": "gen_ai.operation.name", "value": {"stringValue": "execute_tool"}},
                                    {"key": "gen_ai.tool.name", "value": {"stringValue": "stock_order_executor"}},
                                    {"key": "sentinel.run_id", "value": {"stringValue": "custom-run-override"}},
                                ],
                            }
                        ]
                    }
                ],
            }
        ]
    }

    events = parse_otlp_request(json.dumps(raw_json).encode("utf-8"), "application/json")
    assert len(events) == 1
    evt = events[0]

    assert evt.run_id == "custom-run-override"
    assert evt.parent_span_id is None
    assert evt.agent_id == "trading-bot"
    assert evt.team == "quant-team"
    assert evt.span_type == SpanType.TOOL
    assert evt.operation_name == "stock_order_executor"
    assert evt.status == SpanStatus.SUCCEEDED


def test_parse_otlp_json_agent_and_error():
    raw_json = {
        "resourceSpans": [
            {
                "scopeSpans": [
                    {
                        "spans": [
                            {
                                "traceId": "b1b2c3d4e5f60718293a4b5c6d7e8f90",
                                "spanId": "2233445566778899",
                                "name": "plan_step",
                                "startTimeUnixNano": "1700000010000000000",
                                "endTimeUnixNano": "1700000012000000000",
                                "status": {
                                    "code": 2,
                                    "message": "Resource budget exhausted",
                                },
                                "attributes": [
                                    {"key": "gen_ai.operation.name", "value": {"stringValue": "plan"}},
                                    {"key": "gen_ai.agent.name", "value": {"stringValue": "planner-agent"}},
                                ],
                            }
                        ]
                    }
                ]
            }
        ]
    }

    events = parse_otlp_request(json.dumps(raw_json).encode("utf-8"), "application/json")
    assert len(events) == 1
    evt = events[0]

    assert evt.agent_id == "planner-agent"
    assert evt.span_type == SpanType.AGENT
    assert evt.operation_name == "planner-agent"
    assert evt.status == SpanStatus.FAILED
    assert evt.error is not None
    assert evt.error.message == "Resource budget exhausted"


def test_parse_otlp_json_running_span():
    raw_json = {
        "resourceSpans": [
            {
                "scopeSpans": [
                    {
                        "spans": [
                            {
                                "traceId": "c1b2c3d4e5f60718293a4b5c6d7e8f90",
                                "spanId": "3333445566778899",
                                "name": "long_task",
                                "startTimeUnixNano": "1700000020000000000",
                                # No endTimeUnixNano -> running
                            }
                        ]
                    }
                ]
            }
        ]
    }

    events = parse_otlp_request(json.dumps(raw_json).encode("utf-8"), "application/json")
    assert len(events) == 1
    evt = events[0]
    assert evt.status == SpanStatus.RUNNING
    assert evt.ended_at is None
    assert evt.agent_id == "otel-external-agent"
    assert evt.span_type == SpanType.AGENT
    assert evt.operation_name == "long_task"


# ==============================================================================
# 2. Tests for otlp_mapper: parse_otlp_request with Protobuf payloads
# ==============================================================================


def test_parse_otlp_protobuf():
    req = ExportTraceServiceRequest()
    rs = req.resource_spans.add()
    rs.resource.attributes.add(
        key="service.name", value={"string_value": "proto-rag-service"}
    )
    rs.resource.attributes.add(
        key="team", value={"string_value": "rag-team"}
    )

    ss = rs.scope_spans.add()
    s = ss.spans.add()
    trace_bytes = bytes.fromhex("11223344556677889900aabbccddeeff")
    span_bytes = bytes.fromhex("aabbccddeeff0011")
    parent_bytes = bytes.fromhex("0011223344556677")

    s.trace_id = trace_bytes
    s.span_id = span_bytes
    s.parent_span_id = parent_bytes
    s.name = "agent_call"
    s.start_time_unix_nano = 1700000030000000000
    s.end_time_unix_nano = 1700000032000000000
    s.status.code = Status.StatusCode.STATUS_CODE_OK

    s.attributes.add(
        key="gen_ai.operation.name", value={"string_value": "text_completion"}
    )
    s.attributes.add(
        key="gen_ai.provider.name", value={"string_value": "anthropic"}
    )
    s.attributes.add(
        key="gen_ai.request.model", value={"string_value": "claude-3-7-sonnet"}
    )
    s.attributes.add(
        key="gen_ai.usage.input_tokens", value={"int_value": 500}
    )
    s.attributes.add(
        key="gen_ai.usage.output_tokens", value={"int_value": 150}
    )

    raw_bytes = req.SerializeToString()
    events = parse_otlp_request(raw_bytes, "application/x-protobuf")

    assert len(events) == 1
    evt = events[0]

    assert evt.trace_id == "11223344556677889900aabbccddeeff"
    assert evt.span_id == "otel_aabbccddeeff0011"
    assert evt.parent_span_id == "otel_0011223344556677"
    assert evt.run_id == "run_otel_112233445566"
    assert evt.team == "rag-team"
    assert evt.agent_id == "proto-rag-service"
    assert evt.span_type == SpanType.LLM
    assert evt.operation_name == "claude-3-7-sonnet"
    assert evt.status == SpanStatus.SUCCEEDED
    assert evt.model.provider == "anthropic"
    assert evt.model.name == "claude-3-7-sonnet"
    assert evt.usage.input_tokens == 500
    assert evt.usage.output_tokens == 150


# ==============================================================================
# 3. Tests for auth dependency: verify_ingest_auth
# ==============================================================================


@pytest.mark.asyncio
async def test_verify_ingest_auth_with_api_key():
    mock_db = AsyncMock()
    ctx = await verify_ingest_auth(
        x_api_key=settings.SENTINEL_API_KEY,
        authorization=None,
        db=mock_db,
    )
    assert isinstance(ctx, IngestContext)
    assert ctx.team == "demo-sandbox"
    assert ctx.key_id == "env-demo-key"
    assert ctx.is_demo is True


@pytest.mark.asyncio
async def test_verify_ingest_auth_with_bearer():
    mock_db = AsyncMock()
    ctx = await verify_ingest_auth(
        x_api_key=None,
        authorization=f"Bearer {settings.SENTINEL_API_KEY}",
        db=mock_db,
    )
    assert isinstance(ctx, IngestContext)
    assert ctx.team == "demo-sandbox"
    assert ctx.key_id == "env-demo-key"
    assert ctx.is_demo is True


@pytest.mark.asyncio
async def test_verify_ingest_auth_failure():
    mock_db = AsyncMock()
    empty_result = MagicMock()
    empty_result.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = empty_result

    with pytest.raises(HTTPException) as exc_info:
        await verify_ingest_auth(x_api_key="wrong-key", authorization=None, db=mock_db)
    assert exc_info.value.status_code == 401

    with pytest.raises(HTTPException) as exc_info:
        await verify_ingest_auth(x_api_key=None, authorization=None, db=mock_db)
    assert exc_info.value.status_code == 401


# ==============================================================================
# 4. Tests for API endpoint: POST /v1/traces
# ==============================================================================


@pytest.mark.asyncio
async def test_post_otlp_traces_endpoint_json():
    raw_json = {
        "resourceSpans": [
            {
                "resource": {
                    "attributes": [
                        {"key": "service.name", "value": {"stringValue": "support-agent"}}
                    ]
                },
                "scopeSpans": [
                    {
                        "spans": [
                            {
                                "traceId": "11112222333344445555666677778888",
                                "spanId": "9999888877776666",
                                "name": "chat",
                                "startTimeUnixNano": "1700000000000000000",
                                "endTimeUnixNano": "1700000001000000000",
                                "attributes": [
                                    {"key": "gen_ai.operation.name", "value": {"stringValue": "chat"}},
                                    {"key": "gen_ai.request.model", "value": {"stringValue": "gpt-4o"}},
                                ],
                            }
                        ]
                    }
                ],
            }
        ]
    }

    mock_db = AsyncMock()
    app.dependency_overrides[get_db] = lambda: mock_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        with patch(
            "sentinel_backend.api.telemetry.ingest_telemetry_batch",
            new_callable=AsyncMock,
        ) as mock_ingest:
            mock_ingest.return_value = {"accepted": 1, "run_ids": ["run_otel_111122223333"]}

            headers = {
                "Authorization": f"Bearer {settings.SENTINEL_API_KEY}",
                "Content-Type": "application/json",
            }
            resp = await client.post(
                "/v1/traces",
                content=json.dumps(raw_json).encode("utf-8"),
                headers=headers,
            )

            assert resp.status_code == 200
            assert resp.json() == {}
            mock_ingest.assert_awaited_once()
            called_events = mock_ingest.call_args[0][1]
            assert len(called_events) == 1
            assert called_events[0].agent_id == "support-agent"
            assert called_events[0].span_type == SpanType.LLM

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_post_otlp_traces_endpoint_protobuf():
    req = ExportTraceServiceRequest()
    rs = req.resource_spans.add()
    rs.resource.attributes.add(
        key="service.name", value={"string_value": "proto-agent"}
    )
    ss = rs.scope_spans.add()
    s = ss.spans.add()
    s.trace_id = bytes.fromhex("22223333444455556666777788889999")
    s.span_id = bytes.fromhex("1234567890abcdef")
    s.name = "task"
    s.start_time_unix_nano = 1700000000000000000
    s.end_time_unix_nano = 1700000001000000000

    raw_bytes = req.SerializeToString()

    mock_db = AsyncMock()
    app.dependency_overrides[get_db] = lambda: mock_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        with patch(
            "sentinel_backend.api.telemetry.ingest_telemetry_batch",
            new_callable=AsyncMock,
        ) as mock_ingest:
            mock_ingest.return_value = {"accepted": 1, "run_ids": ["run_otel_222233334444"]}

            headers = {
                "X-API-Key": settings.SENTINEL_API_KEY,
                "Content-Type": "application/x-protobuf",
            }
            resp = await client.post(
                "/v1/traces",
                content=raw_bytes,
                headers=headers,
            )

            assert resp.status_code == 200
            assert resp.json() == {}
            mock_ingest.assert_awaited_once()

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_post_otlp_traces_unauthorized():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/v1/traces",
            content=b"{}",
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 401

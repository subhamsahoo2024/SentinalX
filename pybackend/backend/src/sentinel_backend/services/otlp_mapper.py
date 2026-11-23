import base64
import binascii
import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
    ExportTraceServiceRequest,
)
from opentelemetry.proto.common.v1.common_pb2 import AnyValue
from sentinel_sdk.redactor import redact_payload
from sentinel_sdk.schema import (
    CanonicalEventV1,
    CostInfo,
    ErrorInfo,
    ModelInfo,
    SpanStatus,
    SpanType,
    TokenUsage,
)

logger = logging.getLogger(__name__)


def _normalize_id(val: Any) -> str:
    """Normalize trace_id or span_id bytes/string into a lowercase hex string."""
    if not val:
        return ""
    if isinstance(val, bytes):
        return val.hex().lower()
    val_str = str(val).strip()
    if not val_str:
        return ""
    try:
        bytes.fromhex(val_str)
        return val_str.lower()
    except ValueError:
        pass
    try:
        decoded = base64.b64decode(val_str)
        return decoded.hex().lower()
    except (ValueError, binascii.Error):
        return val_str.lower()


def _extract_proto_any_value(val: AnyValue) -> Any:
    """Extract native Python value from OpenTelemetry protobuf AnyValue message."""
    field = val.WhichOneof("value")
    if field is None:
        return None
    raw_val = getattr(val, field)
    if field == "array_value":
        return [_extract_proto_any_value(elem) for elem in raw_val.values]
    if field == "kvlist_value":
        return {
            item.key: _extract_proto_any_value(item.value)
            for item in raw_val.values
        }
    if field == "bytes_value":
        return raw_val.hex()
    return raw_val


def _extract_json_any_value(val: Any) -> Any:
    """Extract native Python value from OpenTelemetry JSON AnyValue representation."""
    if not isinstance(val, dict):
        return val

    if "stringValue" in val:
        return val["stringValue"]
    if "string_value" in val:
        return val["string_value"]
    if "intValue" in val:
        try:
            return int(val["intValue"])
        except (ValueError, TypeError):
            return val["intValue"]
    if "int_value" in val:
        try:
            return int(val["int_value"])
        except (ValueError, TypeError):
            return val["int_value"]
    if "doubleValue" in val:
        try:
            return float(val["doubleValue"])
        except (ValueError, TypeError):
            return val["doubleValue"]
    if "double_value" in val:
        try:
            return float(val["double_value"])
        except (ValueError, TypeError):
            return val["double_value"]
    if "boolValue" in val:
        return bool(val["boolValue"])
    if "bool_value" in val:
        return bool(val["bool_value"])
    if "bytesValue" in val:
        return str(val["bytesValue"])
    if "bytes_value" in val:
        return str(val["bytes_value"])
    if "arrayValue" in val:
        return [
            _extract_json_any_value(x)
            for x in val["arrayValue"].get("values", [])
        ]
    if "array_value" in val:
        return [
            _extract_json_any_value(x)
            for x in val["array_value"].get("values", [])
        ]
    if "kvlistValue" in val:
        return _extract_json_attributes(val["kvlistValue"].get("values", []))
    if "kvlist_value" in val:
        return _extract_json_attributes(val["kvlist_value"].get("values", []))

    return {k: _extract_json_any_value(v) for k, v in val.items()}


def _extract_json_attributes(attrs: Any) -> dict[str, Any]:
    """Parse JSON attribute list into a flattened key-value dict."""
    if isinstance(attrs, dict):
        return {str(k): _extract_json_any_value(v) for k, v in attrs.items()}
    result: dict[str, Any] = {}
    if isinstance(attrs, list):
        for item in attrs:
            if isinstance(item, dict):
                k = item.get("key")
                if k is not None:
                    result[str(k)] = _extract_json_any_value(item.get("value"))
    return result


def _to_int(val: Any) -> int | None:
    if val is None:
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


def _nano_to_utc_datetime(nano: Any) -> datetime | None:
    if nano is None:
        return None
    try:
        val = int(nano)
        if val <= 0:
            return None
        return datetime.fromtimestamp(val / 1_000_000_000, tz=UTC)
    except (ValueError, TypeError, OSError):
        return None


def _is_status_error(status_code: Any) -> bool:
    if status_code == 2:
        return True
    if isinstance(status_code, str):
        return status_code in ("2", "STATUS_CODE_ERROR", "ERROR")
    return False


def _map_span_to_canonical_event(
    trace_id_hex: str,
    span_id_hex: str,
    parent_span_id_hex: str,
    span_name: str,
    start_nano: Any,
    end_nano: Any,
    status_code: Any,
    status_message: str | None,
    span_attrs: dict[str, Any],
    resource_attrs: dict[str, Any],
) -> CanonicalEventV1:
    """Map normalized OpenTelemetry span data and attributes to CanonicalEventV1."""
    # 1. trace_id & run_id
    trace_id = trace_id_hex
    custom_run_id = span_attrs.get("sentinel.run_id")
    run_id = (
        str(custom_run_id)
        if custom_run_id
        else f"run_otel_{trace_id[:12]}"
    )

    # 2. span_id & parent_span_id
    span_id = f"otel_{span_id_hex}"
    is_parent_empty = (
        not parent_span_id_hex
        or not parent_span_id_hex.replace("0", "")
    )
    parent_span_id = None if is_parent_empty else f"otel_{parent_span_id_hex}"

    # 3. Resource attributes: service.name, team / deployment.environment
    team = str(
        resource_attrs.get("team")
        or resource_attrs.get("deployment.environment")
        or "default"
    )

    # 4. agent_id & agent_name
    agent_id = str(
        span_attrs.get("gen_ai.agent.id")
        or span_attrs.get("gen_ai.agent.name")
        or resource_attrs.get("service.name")
        or "otel-external-agent"
    )
    agent_name_raw = (
        span_attrs.get("gen_ai.agent.name")
        or resource_attrs.get("service.name")
    )
    agent_name = str(agent_name_raw) if agent_name_raw is not None else None

    # 5. span_type & operation_name from gen_ai.operation.name
    gen_ai_op = span_attrs.get("gen_ai.operation.name")
    if gen_ai_op in ("chat", "text_completion"):
        span_type = SpanType.LLM
        op_name_val = span_attrs.get("gen_ai.request.model") or span_name or "chat"
    elif gen_ai_op == "execute_tool":
        span_type = SpanType.TOOL
        op_name_val = span_attrs.get("gen_ai.tool.name") or span_name or "execute_tool"
    elif gen_ai_op in ("invoke_agent", "invoke_workflow", "plan"):
        span_type = SpanType.AGENT
        op_name_val = span_attrs.get("gen_ai.agent.name") or span_name or str(gen_ai_op)
    else:
        span_type = SpanType.AGENT
        op_name_val = span_name or "agent"
    operation_name = str(op_name_val) if op_name_val else "span"

    # 6. model: ModelInfo(provider=attr("gen_ai.provider.name") or attr("gen_ai.system"), name=attr("gen_ai.request.model") or attr("gen_ai.response.model"))
    provider = span_attrs.get("gen_ai.provider.name") or span_attrs.get("gen_ai.system")
    model_name = span_attrs.get("gen_ai.request.model") or span_attrs.get("gen_ai.response.model")
    model = ModelInfo(
        provider=str(provider) if provider is not None else None,
        name=str(model_name) if model_name is not None else None,
    )

    # 7. usage: TokenUsage(input_tokens=attr("gen_ai.usage.input_tokens"), output_tokens=attr("gen_ai.usage.output_tokens"))
    in_tok = _to_int(
        span_attrs.get("gen_ai.usage.input_tokens")
        or span_attrs.get("gen_ai.usage.prompt_tokens")
    )
    out_tok = _to_int(
        span_attrs.get("gen_ai.usage.output_tokens")
        or span_attrs.get("gen_ai.usage.completion_tokens")
    )
    usage = TokenUsage(
        input_tokens=in_tok,
        output_tokens=out_tok,
    )

    # 8. started_at / ended_at
    started_at = _nano_to_utc_datetime(start_nano) or datetime.now(UTC)
    ended_at = _nano_to_utc_datetime(end_nano)

    # 9. status
    # SpanStatus.FAILED if OTel status code is 2 (STATUS_CODE_ERROR),
    # else SpanStatus.SUCCEEDED if endTimeUnixNano is present, else SpanStatus.RUNNING.
    has_end_time = end_nano is not None and _to_int(end_nano) is not None and _to_int(end_nano) > 0  # type: ignore[operator]
    if _is_status_error(status_code):
        span_status = SpanStatus.FAILED
    elif has_end_time:
        span_status = SpanStatus.SUCCEEDED
    else:
        span_status = SpanStatus.RUNNING

    error: ErrorInfo | None = None
    if span_status == SpanStatus.FAILED:
        error = ErrorInfo(
            error_class="OpenTelemetryError",
            message=str(status_message) if status_message else "Span failed with STATUS_CODE_ERROR",
        )

    # 10. Redact all extracted span attributes
    redacted_attributes = redact_payload(span_attrs)
    if not isinstance(redacted_attributes, dict):
        redacted_attributes = {"raw": redacted_attributes}

    return CanonicalEventV1(
        event_id=f"evt_{uuid.uuid4().hex[:12]}",
        trace_id=trace_id,
        span_id=span_id,
        parent_span_id=parent_span_id,
        run_id=run_id,
        agent_id=agent_id,
        agent_name=agent_name,
        team=team,
        framework="opentelemetry",
        attempt_number=1,
        span_type=span_type,
        operation_name=operation_name,
        status=span_status,
        started_at=started_at,
        ended_at=ended_at,
        model=model,
        usage=usage,
        cost=CostInfo(),
        error=error,
        attributes=redacted_attributes,
    )


def parse_otlp_request(raw_body: bytes, content_type: str) -> list[CanonicalEventV1]:
    """Parse OpenTelemetry OTLP/HTTP export trace request into a list of CanonicalEventV1 events.

    Supports both application/x-protobuf and application/json payloads.
    """
    if not raw_body:
        return []

    events: list[CanonicalEventV1] = []

    if "application/x-protobuf" in (content_type or "").lower():
        req = ExportTraceServiceRequest()
        try:
            req.ParseFromString(raw_body)
        except Exception as exc:
            raise ValueError(f"Failed to parse OTLP protobuf payload: {exc}") from exc

        for rs in req.resource_spans:
            resource_attrs = {
                kv.key: _extract_proto_any_value(kv.value)
                for kv in rs.resource.attributes
            }
            for ss in rs.scope_spans:
                for s in ss.spans:
                    span_attrs = {
                        kv.key: _extract_proto_any_value(kv.value)
                        for kv in s.attributes
                    }
                    event = _map_span_to_canonical_event(
                        trace_id_hex=s.trace_id.hex().lower(),
                        span_id_hex=s.span_id.hex().lower(),
                        parent_span_id_hex=s.parent_span_id.hex().lower() if s.parent_span_id else "",
                        span_name=s.name,
                        start_nano=s.start_time_unix_nano,
                        end_nano=s.end_time_unix_nano,
                        status_code=s.status.code,
                        status_message=s.status.message or None,
                        span_attrs=span_attrs,
                        resource_attrs=resource_attrs,
                    )
                    events.append(event)
    else:
        try:
            payload_str = raw_body.decode("utf-8")
            data = json.loads(payload_str)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"Failed to parse OTLP JSON payload: {exc}") from exc

        if not isinstance(data, dict):
            return []

        resource_spans = data.get("resourceSpans") or data.get("resource_spans") or []
        for rs in resource_spans:
            if not isinstance(rs, dict):
                continue
            resource = rs.get("resource") or {}
            resource_attrs = _extract_json_attributes(
                resource.get("attributes") or []
            )

            scope_spans = rs.get("scopeSpans") or rs.get("scope_spans") or []
            for ss in scope_spans:
                if not isinstance(ss, dict):
                    continue
                spans = ss.get("spans") or []
                for s in spans:
                    if not isinstance(s, dict):
                        continue
                    span_attrs = _extract_json_attributes(
                        s.get("attributes") or []
                    )
                    status_obj = s.get("status") or {}

                    event = _map_span_to_canonical_event(
                        trace_id_hex=_normalize_id(s.get("traceId") or s.get("trace_id")),
                        span_id_hex=_normalize_id(s.get("spanId") or s.get("span_id")),
                        parent_span_id_hex=_normalize_id(s.get("parentSpanId") or s.get("parent_span_id")),
                        span_name=s.get("name") or "",
                        start_nano=s.get("startTimeUnixNano") or s.get("start_time_unix_nano"),
                        end_nano=s.get("endTimeUnixNano") or s.get("end_time_unix_nano"),
                        status_code=status_obj.get("code"),
                        status_message=status_obj.get("message"),
                        span_attrs=span_attrs,
                        resource_attrs=resource_attrs,
                    )
                    events.append(event)

    return events


__all__ = ["parse_otlp_request"]

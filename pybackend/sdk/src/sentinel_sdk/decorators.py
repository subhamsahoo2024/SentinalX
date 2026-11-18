import functools
import inspect
import traceback
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from sentinel_sdk.context import (
    get_agent_id,
    get_agent_name,
    get_current_span_id,
    get_run_id,
    get_team,
    get_trace_id,
    next_attempt_number,
    set_agent_id,
    set_agent_name,
    set_current_span_id,
    set_run_id,
    set_team,
    set_trace_id,
)
from sentinel_sdk.exporter import get_exporter
from sentinel_sdk.redactor import redact_payload
from sentinel_sdk.schema import (
    CanonicalEventV1,
    ErrorInfo,
    ModelInfo,
    SpanStatus,
    SpanType,
    TokenUsage,
)


def _extract_inputs(
    fn: Callable[..., Any], args: tuple[Any, ...], kwargs: dict[str, Any]
) -> dict[str, Any]:
    """Capture and redact function arguments."""
    try:
        sig = inspect.signature(fn)
        bound = sig.bind_partial(*args, **kwargs)
        bound.apply_defaults()
        raw_inputs = {
            k: v
            for k, v in bound.arguments.items()
            if k not in ("self", "cls")
        }
        return redact_payload(raw_inputs)
    except (ValueError, TypeError):
        return {
            "args": redact_payload(list(args)),
            "kwargs": redact_payload(kwargs),
        }


def _extract_token_usage(result: Any) -> TokenUsage | None:
    """Extract TokenUsage from return value if usage information is present."""
    if result is None:
        return None

    usage_obj = None
    if isinstance(result, dict):
        if "usage" in result:
            usage_obj = result["usage"]
        elif (
            "input_tokens" in result
            or "output_tokens" in result
            or "prompt_tokens" in result
        ):
            usage_obj = result
    elif hasattr(result, "usage"):
        usage_obj = result.usage
    elif (
        hasattr(result, "input_tokens")
        or hasattr(result, "output_tokens")
        or hasattr(result, "prompt_tokens")
    ):
        usage_obj = result

    if usage_obj is None:
        return None

    if isinstance(usage_obj, TokenUsage):
        return usage_obj

    in_tok: Any = None
    out_tok: Any = None
    cached_tok: Any = None

    if isinstance(usage_obj, dict):
        in_tok = usage_obj.get("input_tokens", usage_obj.get("prompt_tokens"))
        out_tok = usage_obj.get(
            "output_tokens", usage_obj.get("completion_tokens")
        )
        cached_tok = usage_obj.get("cached_tokens")
    else:
        in_tok = getattr(
            usage_obj,
            "input_tokens",
            getattr(usage_obj, "prompt_tokens", None),
        )
        out_tok = getattr(
            usage_obj,
            "output_tokens",
            getattr(usage_obj, "completion_tokens", None),
        )
        cached_tok = getattr(usage_obj, "cached_tokens", None)

    try:
        in_val = int(in_tok) if in_tok is not None else None
    except (ValueError, TypeError):
        in_val = None

    try:
        out_val = int(out_tok) if out_tok is not None else None
    except (ValueError, TypeError):
        out_val = None

    try:
        cached_val = int(cached_tok) if cached_tok is not None else None
    except (ValueError, TypeError):
        cached_val = None

    if in_val is not None or out_val is not None or cached_val is not None:
        return TokenUsage(
            input_tokens=in_val,
            output_tokens=out_val,
            cached_tokens=cached_val,
        )
    return None


def _trace_invocation(
    fn: Callable[..., Any],
    span_type: SpanType,
    operation_name: str,
    agent_id: str | None = None,
    agent_name: str | None = None,
    team: str = "default",
    framework: str = "custom",
    model_info: ModelInfo | None = None,
) -> Callable[..., Any]:
    """Internal higher-order function wrapping sync and async callables with Sentinel tracing."""

    if inspect.iscoroutinefunction(fn):

        @functools.wraps(fn)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            span_id = f"span_{uuid.uuid4().hex[:12]}"
            parent_span_id = get_current_span_id()
            started_at = datetime.now(UTC)

            run_id = get_run_id() or f"run_{uuid.uuid4().hex[:12]}"
            trace_id = get_trace_id() or uuid.uuid4().hex

            eff_agent_id = agent_id or get_agent_id() or "default-agent"
            eff_agent_name = agent_name or get_agent_name()
            eff_team = team or get_team()
            eff_framework = framework

            attempt_number = next_attempt_number(
                run_id, eff_agent_id, operation_name
            )

            inputs = _extract_inputs(fn, args, kwargs)
            start_event = CanonicalEventV1(
                event_id=f"evt_{uuid.uuid4().hex[:12]}",
                trace_id=trace_id,
                span_id=span_id,
                parent_span_id=parent_span_id,
                run_id=run_id,
                agent_id=eff_agent_id,
                agent_name=eff_agent_name,
                team=eff_team,
                framework=eff_framework,
                attempt_number=attempt_number,
                span_type=span_type,
                operation_name=operation_name,
                status=SpanStatus.RUNNING,
                started_at=started_at,
                ended_at=None,
                model=model_info,
                usage=None,
                attributes={"inputs": inputs},
            )
            get_exporter().enqueue(start_event)

            prev_span_id = parent_span_id
            prev_run_id = get_run_id()
            prev_trace_id = get_trace_id()
            prev_agent_id = get_agent_id()
            prev_agent_name = get_agent_name()
            prev_team = get_team()

            set_current_span_id(span_id)
            set_run_id(run_id)
            set_trace_id(trace_id)
            if agent_id is not None:
                set_agent_id(eff_agent_id)
            if eff_agent_name is not None:
                set_agent_name(eff_agent_name)
            if eff_team is not None:
                set_team(eff_team)

            try:
                result = await fn(*args, **kwargs)
                ended_at = datetime.now(UTC)
                token_usage = _extract_token_usage(result)
                attributes = {
                    "inputs": inputs,
                    "output": redact_payload(result),
                }
                success_event = CanonicalEventV1(
                    event_id=f"evt_{uuid.uuid4().hex[:12]}",
                    trace_id=trace_id,
                    span_id=span_id,
                    parent_span_id=parent_span_id,
                    run_id=run_id,
                    agent_id=eff_agent_id,
                    agent_name=eff_agent_name,
                    team=eff_team,
                    framework=eff_framework,
                    attempt_number=attempt_number,
                    span_type=span_type,
                    operation_name=operation_name,
                    status=SpanStatus.SUCCEEDED,
                    started_at=started_at,
                    ended_at=ended_at,
                    model=model_info,
                    usage=token_usage,
                    attributes=attributes,
                )
                get_exporter().enqueue(success_event)
                return result
            except BaseException as exc:
                ended_at = datetime.now(UTC)
                error_info = ErrorInfo(
                    error_class=type(exc).__name__,
                    message=str(exc),
                    stack_summary=traceback.format_exc(),
                )
                attributes = {"inputs": inputs}
                fail_event = CanonicalEventV1(
                    event_id=f"evt_{uuid.uuid4().hex[:12]}",
                    trace_id=trace_id,
                    span_id=span_id,
                    parent_span_id=parent_span_id,
                    run_id=run_id,
                    agent_id=eff_agent_id,
                    agent_name=eff_agent_name,
                    team=eff_team,
                    framework=eff_framework,
                    attempt_number=attempt_number,
                    span_type=span_type,
                    operation_name=operation_name,
                    status=SpanStatus.FAILED,
                    started_at=started_at,
                    ended_at=ended_at,
                    model=model_info,
                    usage=None,
                    error=error_info,
                    attributes=attributes,
                )
                get_exporter().enqueue(fail_event)
                raise
            finally:
                set_current_span_id(prev_span_id)
                set_run_id(prev_run_id)
                set_trace_id(prev_trace_id)
                set_agent_id(prev_agent_id)
                set_agent_name(prev_agent_name)
                set_team(prev_team)

        return async_wrapper

    @functools.wraps(fn)
    def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
        span_id = f"span_{uuid.uuid4().hex[:12]}"
        parent_span_id = get_current_span_id()
        started_at = datetime.now(UTC)

        run_id = get_run_id() or f"run_{uuid.uuid4().hex[:12]}"
        trace_id = get_trace_id() or uuid.uuid4().hex

        eff_agent_id = agent_id or get_agent_id() or "default-agent"
        eff_agent_name = agent_name or get_agent_name()
        eff_team = team or get_team()
        eff_framework = framework

        attempt_number = next_attempt_number(
            run_id, eff_agent_id, operation_name
        )

        inputs = _extract_inputs(fn, args, kwargs)
        start_event = CanonicalEventV1(
            event_id=f"evt_{uuid.uuid4().hex[:12]}",
            trace_id=trace_id,
            span_id=span_id,
            parent_span_id=parent_span_id,
            run_id=run_id,
            agent_id=eff_agent_id,
            agent_name=eff_agent_name,
            team=eff_team,
            framework=eff_framework,
            attempt_number=attempt_number,
            span_type=span_type,
            operation_name=operation_name,
            status=SpanStatus.RUNNING,
            started_at=started_at,
            ended_at=None,
            model=model_info,
            usage=None,
            attributes={"inputs": inputs},
        )
        get_exporter().enqueue(start_event)

        prev_span_id = parent_span_id
        prev_run_id = get_run_id()
        prev_trace_id = get_trace_id()
        prev_agent_id = get_agent_id()
        prev_agent_name = get_agent_name()
        prev_team = get_team()

        set_current_span_id(span_id)
        set_run_id(run_id)
        set_trace_id(trace_id)
        if agent_id is not None:
            set_agent_id(eff_agent_id)
        if eff_agent_name is not None:
            set_agent_name(eff_agent_name)
        if eff_team is not None:
            set_team(eff_team)

        try:
            result = fn(*args, **kwargs)
            ended_at = datetime.now(UTC)
            token_usage = _extract_token_usage(result)
            attributes = {
                "inputs": inputs,
                "output": redact_payload(result),
            }
            success_event = CanonicalEventV1(
                event_id=f"evt_{uuid.uuid4().hex[:12]}",
                trace_id=trace_id,
                span_id=span_id,
                parent_span_id=parent_span_id,
                run_id=run_id,
                agent_id=eff_agent_id,
                agent_name=eff_agent_name,
                team=eff_team,
                framework=eff_framework,
                attempt_number=attempt_number,
                span_type=span_type,
                operation_name=operation_name,
                status=SpanStatus.SUCCEEDED,
                started_at=started_at,
                ended_at=ended_at,
                model=model_info,
                usage=token_usage,
                attributes=attributes,
            )
            get_exporter().enqueue(success_event)
            return result
        except BaseException as exc:
            ended_at = datetime.now(UTC)
            error_info = ErrorInfo(
                error_class=type(exc).__name__,
                message=str(exc),
                stack_summary=traceback.format_exc(),
            )
            attributes = {"inputs": inputs}
            fail_event = CanonicalEventV1(
                event_id=f"evt_{uuid.uuid4().hex[:12]}",
                trace_id=trace_id,
                span_id=span_id,
                parent_span_id=parent_span_id,
                run_id=run_id,
                agent_id=eff_agent_id,
                agent_name=eff_agent_name,
                team=eff_team,
                framework=eff_framework,
                attempt_number=attempt_number,
                span_type=span_type,
                operation_name=operation_name,
                status=SpanStatus.FAILED,
                started_at=started_at,
                ended_at=ended_at,
                model=model_info,
                usage=None,
                error=error_info,
                attributes=attributes,
            )
            get_exporter().enqueue(fail_event)
            raise
        finally:
            set_current_span_id(prev_span_id)
            set_run_id(prev_run_id)
            set_trace_id(prev_trace_id)
            set_agent_id(prev_agent_id)
            set_agent_name(prev_agent_name)
            set_team(prev_team)

    return sync_wrapper


def trace_agent(
    agent_id: str,
    name: str | None = None,
    team: str = "default",
    framework: str = "custom",
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator to trace agent execution spans."""

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        return _trace_invocation(
            fn=fn,
            span_type=SpanType.AGENT,
            operation_name=fn.__name__,
            agent_id=agent_id,
            agent_name=name,
            team=team,
            framework=framework,
        )

    return decorator


def trace_llm(
    provider: str,
    model: str,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator to trace LLM calls."""
    model_info = ModelInfo(provider=provider, name=model)

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        return _trace_invocation(
            fn=fn,
            span_type=SpanType.LLM,
            operation_name=fn.__name__,
            model_info=model_info,
        )

    return decorator


def trace_tool(
    tool_name: str | Callable[..., Any] | None = None,
) -> Any:
    """Decorator to trace tool executions. Supports both @trace_tool and @trace_tool('name')."""
    if callable(tool_name):
        fn = tool_name
        return _trace_invocation(
            fn=fn,
            span_type=SpanType.TOOL,
            operation_name=fn.__name__,
        )

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        op_name = (
            tool_name if isinstance(tool_name, str) and tool_name else fn.__name__
        )
        return _trace_invocation(
            fn=fn,
            span_type=SpanType.TOOL,
            operation_name=op_name,
        )

    return decorator


__all__ = [
    "trace_agent",
    "trace_llm",
    "trace_tool",
]

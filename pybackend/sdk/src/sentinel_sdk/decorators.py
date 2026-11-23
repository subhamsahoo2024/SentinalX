import asyncio
import functools
import inspect
import logging
import time
import traceback
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import httpx

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
from sentinel_sdk.exceptions import (
    BudgetCircuitBreakerError,
    GovernanceRejectedError,
    GovernanceTimeoutError,
    RunCancelledError,
    SentinelGovernanceError,
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

logger = logging.getLogger(__name__)


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


def _resolve_sentinel_config() -> tuple[str, str]:
    exporter = get_exporter()
    if (
        exporter
        and getattr(exporter, "base_url", None)
        and getattr(exporter, "api_key", None)
    ):
        return exporter.base_url, exporter.api_key
    from sentinel_sdk.config import load_sdk_env

    return load_sdk_env()


_CONTROL_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_CONTROL_CACHE_TTL = 0.25
_http_client: httpx.Client | None = None


def _get_http_client() -> httpx.Client:
    global _http_client
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.Client(timeout=0.5)
    return _http_client


def _check_runtime_control(run_id: str) -> dict[str, Any]:
    """Check active runtime control state with 0.25s TTL in-memory cache.

    Fails open on network/HTTP errors or unconfigured URL so telemetry never crashes offline runs.
    """
    now = time.monotonic()
    cached = _CONTROL_CACHE.get(run_id)
    if cached is not None and (now - cached[0]) < _CONTROL_CACHE_TTL:
        return cached[1]

    default_state: dict[str, Any] = {"cancelled": False, "blocked_reason": None}
    try:
        base_url, api_key = _resolve_sentinel_config()
        if not base_url or not api_key:
            return default_state

        if "localhost" in base_url:
            base_url = base_url.replace("localhost", "127.0.0.1")

        url = f"{base_url.rstrip('/')}/api/runs/{run_id}/control-state"
        headers = {"X-API-Key": api_key}
        client = _get_http_client()
        resp = client.get(url, headers=headers)
        if resp.status_code == 200:
            data = resp.json()
            state = {
                "cancelled": bool(data.get("cancelled", False)),
                "blocked_reason": data.get("blocked_reason"),
            }
            _CONTROL_CACHE[run_id] = (time.monotonic(), state)
            return state
    except Exception as e:  # noqa: BLE001
        logger.debug("Runtime control check failed: %s", e)

    return default_state


def _handle_runtime_control_gate(
    span_type: SpanType,
    run_id: str,
    trace_id: str,
    span_id: str,
    parent_span_id: str | None,
    eff_agent_id: str,
    eff_agent_name: str | None,
    eff_team: str,
    eff_framework: str,
    attempt_number: int,
    operation_name: str,
    started_at: datetime,
    model_info: ModelInfo | None,
    inputs: dict[str, Any],
) -> None:
    if span_type not in (SpanType.LLM, SpanType.TOOL):
        return

    ctrl = _check_runtime_control(run_id)
    if ctrl.get("cancelled"):
        ended_at = datetime.now(UTC)
        error_info = ErrorInfo(
            error_class="RunCancelledError",
            message="Run aborted by operator kill-switch",
            stack_summary=None,
        )
        cancelled_event = CanonicalEventV1(
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
            status=SpanStatus.CANCELLED,
            started_at=started_at,
            ended_at=ended_at,
            model=model_info,
            usage=None,
            error=error_info,
            attributes={"inputs": inputs},
        )
        get_exporter().enqueue(cancelled_event)
        get_exporter().flush()
        raise RunCancelledError("Run aborted by operator kill-switch")

    if span_type == SpanType.LLM and ctrl.get("blocked_reason"):
        blocked_reason = ctrl["blocked_reason"]
        ended_at = datetime.now(UTC)
        error_info = ErrorInfo(
            error_class="BudgetCircuitBreakerError",
            message=f"Blocked by policy: {blocked_reason}",
            stack_summary=None,
        )
        blocked_event = CanonicalEventV1(
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
            status=SpanStatus.CANCELLED,
            started_at=started_at,
            ended_at=ended_at,
            model=model_info,
            usage=None,
            error=error_info,
            attributes={"inputs": inputs},
        )
        get_exporter().enqueue(blocked_event)
        get_exporter().flush()
        raise BudgetCircuitBreakerError(f"Blocked by policy: {blocked_reason}")


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
            _handle_runtime_control_gate(
                span_type=span_type,
                run_id=run_id,
                trace_id=trace_id,
                span_id=span_id,
                parent_span_id=parent_span_id,
                eff_agent_id=eff_agent_id,
                eff_agent_name=eff_agent_name,
                eff_team=eff_team,
                eff_framework=eff_framework,
                attempt_number=attempt_number,
                operation_name=operation_name,
                started_at=started_at,
                model_info=model_info,
                inputs=inputs,
            )
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
                fail_status = (
                    SpanStatus.CANCELLED
                    if isinstance(exc, (RunCancelledError, BudgetCircuitBreakerError))
                    else SpanStatus.FAILED
                )
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
                    status=fail_status,
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
        _handle_runtime_control_gate(
            span_type=span_type,
            run_id=run_id,
            trace_id=trace_id,
            span_id=span_id,
            parent_span_id=parent_span_id,
            eff_agent_id=eff_agent_id,
            eff_agent_name=eff_agent_name,
            eff_team=eff_team,
            eff_framework=eff_framework,
            attempt_number=attempt_number,
            operation_name=operation_name,
            started_at=started_at,
            model_info=model_info,
            inputs=inputs,
        )
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
            fail_status = (
                SpanStatus.CANCELLED
                if isinstance(exc, (RunCancelledError, BudgetCircuitBreakerError))
                else SpanStatus.FAILED
            )
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
                status=fail_status,
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


async def _execute_async_gate(
    fn: Callable[..., Any],
    tool_name: str,
    risk_level: str,
    policy_reason: str,
    timeout_seconds: int,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
) -> Any:
    span_id = f"span_{uuid.uuid4().hex[:12]}"
    parent_span_id = get_current_span_id()
    started_at = datetime.now(UTC)

    run_id = get_run_id() or f"run_{uuid.uuid4().hex[:12]}"
    trace_id = get_trace_id() or uuid.uuid4().hex

    eff_agent_id = get_agent_id() or "default-agent"
    eff_agent_name = get_agent_name()
    eff_team = get_team()

    attempt_number = next_attempt_number(run_id, eff_agent_id, tool_name)
    inputs = _extract_inputs(fn, args, kwargs)

    # a) Emit CanonicalEventV1 with status=SpanStatus.AWAITING_APPROVAL
    awaiting_event = CanonicalEventV1(
        event_id=f"evt_{uuid.uuid4().hex[:12]}",
        trace_id=trace_id,
        span_id=span_id,
        parent_span_id=parent_span_id,
        run_id=run_id,
        agent_id=eff_agent_id,
        agent_name=eff_agent_name,
        team=eff_team,
        framework="custom",
        attempt_number=attempt_number,
        span_type=SpanType.TOOL,
        operation_name=tool_name,
        status=SpanStatus.AWAITING_APPROVAL,
        started_at=started_at,
        ended_at=None,
        model=None,
        usage=None,
        attributes={"inputs": inputs},
    )
    get_exporter().enqueue(awaiting_event)

    # b) Flush immediately so span is persisted in DB before requesting approval
    get_exporter().flush(timeout=5.0)

    base_url, api_key = _resolve_sentinel_config()
    headers = {
        "Content-Type": "application/json",
        "X-API-Key": api_key,
    }
    req_payload = {
        "run_id": run_id,
        "span_id": span_id,
        "agent_id": eff_agent_id,
        "tool_name": tool_name,
        "sanitized_args": inputs,
        "risk_level": risk_level,
        "policy_reason": policy_reason,
    }

    prev_span_id = parent_span_id
    set_current_span_id(span_id)

    try:
        # c) POST to {SENTINEL_URL}/api/approvals/request
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    f"{base_url}/api/approvals/request",
                    json=req_payload,
                    headers=headers,
                )
                resp.raise_for_status()
                approval_data = resp.json()
                approval_id = approval_data["approval_id"]
        except httpx.HTTPError as exc:
            ended_at = datetime.now(UTC)
            error_info = ErrorInfo(
                error_class=type(exc).__name__,
                message=f"Failed to submit approval request: {exc}",
                stack_summary=traceback.format_exc(),
            )
            fail_event = CanonicalEventV1(
                event_id=f"evt_{uuid.uuid4().hex[:12]}",
                trace_id=trace_id,
                span_id=span_id,
                parent_span_id=parent_span_id,
                run_id=run_id,
                agent_id=eff_agent_id,
                agent_name=eff_agent_name,
                team=eff_team,
                framework="custom",
                attempt_number=attempt_number,
                span_type=SpanType.TOOL,
                operation_name=tool_name,
                status=SpanStatus.FAILED,
                started_at=started_at,
                ended_at=ended_at,
                model=None,
                usage=None,
                error=error_info,
                attributes={"inputs": inputs},
            )
            get_exporter().enqueue(fail_event)
            get_exporter().flush(timeout=5.0)
            raise SentinelGovernanceError(
                f"Failed to submit approval request for tool '{tool_name}': {exc}"
            ) from exc

        # d) Poll GET {SENTINEL_URL}/api/approvals/{approval_id}/wait?timeout=20
        start_poll = time.monotonic()
        decision_status: str | None = None
        decision_data: dict[str, Any] = {}

        async with httpx.AsyncClient(timeout=30.0) as client:
            while True:
                elapsed = time.monotonic() - start_poll
                remaining = timeout_seconds - elapsed
                if remaining <= 0:
                    break
                wait_timeout = min(20, max(1, int(remaining)))
                try:
                    poll_resp = await client.get(
                        f"{base_url}/api/approvals/{approval_id}/wait?timeout={wait_timeout}",
                        headers=headers,
                        timeout=float(wait_timeout + 5),
                    )
                    if poll_resp.is_success:
                        decision_data = poll_resp.json()
                        current_status = decision_data.get("status")
                        if current_status in ("APPROVED", "REJECTED"):
                            decision_status = current_status
                            break
                except httpx.TimeoutException:
                    pass
                except httpx.HTTPError:
                    await asyncio.sleep(0.5)

        # e) If APPROVED:
        if decision_status == "APPROVED":
            running_event = CanonicalEventV1(
                event_id=f"evt_{uuid.uuid4().hex[:12]}",
                trace_id=trace_id,
                span_id=span_id,
                parent_span_id=parent_span_id,
                run_id=run_id,
                agent_id=eff_agent_id,
                agent_name=eff_agent_name,
                team=eff_team,
                framework="custom",
                attempt_number=attempt_number,
                span_type=SpanType.TOOL,
                operation_name=tool_name,
                status=SpanStatus.RUNNING,
                started_at=started_at,
                ended_at=None,
                model=None,
                usage=None,
                attributes={"inputs": inputs},
            )
            get_exporter().enqueue(running_event)

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
                    framework="custom",
                    attempt_number=attempt_number,
                    span_type=SpanType.TOOL,
                    operation_name=tool_name,
                    status=SpanStatus.SUCCEEDED,
                    started_at=started_at,
                    ended_at=ended_at,
                    model=None,
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
                fail_event = CanonicalEventV1(
                    event_id=f"evt_{uuid.uuid4().hex[:12]}",
                    trace_id=trace_id,
                    span_id=span_id,
                    parent_span_id=parent_span_id,
                    run_id=run_id,
                    agent_id=eff_agent_id,
                    agent_name=eff_agent_name,
                    team=eff_team,
                    framework="custom",
                    attempt_number=attempt_number,
                    span_type=SpanType.TOOL,
                    operation_name=tool_name,
                    status=SpanStatus.FAILED,
                    started_at=started_at,
                    ended_at=ended_at,
                    model=None,
                    usage=None,
                    error=error_info,
                    attributes={"inputs": inputs},
                )
                get_exporter().enqueue(fail_event)
                raise

        # f) If REJECTED:
        elif decision_status == "REJECTED":
            ended_at = datetime.now(UTC)
            rejection_comment = (
                decision_data.get("comment")
                or "Tool execution rejected by human approver"
            )
            error_info = ErrorInfo(
                error_class="GovernanceRejectedError",
                message=f"Tool execution '{tool_name}' was rejected: {rejection_comment}",
            )
            attributes = {
                "inputs": inputs,
                "rejection": {
                    "decided_by": decision_data.get("decided_by"),
                    "comment": decision_data.get("comment"),
                },
            }
            cancelled_event = CanonicalEventV1(
                event_id=f"evt_{uuid.uuid4().hex[:12]}",
                trace_id=trace_id,
                span_id=span_id,
                parent_span_id=parent_span_id,
                run_id=run_id,
                agent_id=eff_agent_id,
                agent_name=eff_agent_name,
                team=eff_team,
                framework="custom",
                attempt_number=attempt_number,
                span_type=SpanType.TOOL,
                operation_name=tool_name,
                status=SpanStatus.CANCELLED,
                started_at=started_at,
                ended_at=ended_at,
                model=None,
                usage=None,
                error=error_info,
                attributes=attributes,
            )
            get_exporter().enqueue(cancelled_event)
            get_exporter().flush(timeout=5.0)
            raise GovernanceRejectedError(
                f"Tool execution '{tool_name}' was rejected by human approver: {rejection_comment}"
            )

        # Timed out:
        else:
            ended_at = datetime.now(UTC)
            error_info = ErrorInfo(
                error_class="GovernanceTimeoutError",
                message=(
                    f"Tool execution '{tool_name}' timed out after "
                    f"{timeout_seconds}s waiting for human approval"
                ),
            )
            timed_out_event = CanonicalEventV1(
                event_id=f"evt_{uuid.uuid4().hex[:12]}",
                trace_id=trace_id,
                span_id=span_id,
                parent_span_id=parent_span_id,
                run_id=run_id,
                agent_id=eff_agent_id,
                agent_name=eff_agent_name,
                team=eff_team,
                framework="custom",
                attempt_number=attempt_number,
                span_type=SpanType.TOOL,
                operation_name=tool_name,
                status=SpanStatus.TIMED_OUT,
                started_at=started_at,
                ended_at=ended_at,
                model=None,
                usage=None,
                error=error_info,
                attributes={"inputs": inputs},
            )
            get_exporter().enqueue(timed_out_event)
            get_exporter().flush(timeout=5.0)
            raise GovernanceTimeoutError(
                f"Tool execution '{tool_name}' timed out after {timeout_seconds}s waiting for human approval"
            )
    finally:
        set_current_span_id(prev_span_id)


def _execute_sync_gate(
    fn: Callable[..., Any],
    tool_name: str,
    risk_level: str,
    policy_reason: str,
    timeout_seconds: int,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
) -> Any:
    span_id = f"span_{uuid.uuid4().hex[:12]}"
    parent_span_id = get_current_span_id()
    started_at = datetime.now(UTC)

    run_id = get_run_id() or f"run_{uuid.uuid4().hex[:12]}"
    trace_id = get_trace_id() or uuid.uuid4().hex

    eff_agent_id = get_agent_id() or "default-agent"
    eff_agent_name = get_agent_name()
    eff_team = get_team()

    attempt_number = next_attempt_number(run_id, eff_agent_id, tool_name)
    inputs = _extract_inputs(fn, args, kwargs)

    # a) Emit CanonicalEventV1 with status=SpanStatus.AWAITING_APPROVAL
    awaiting_event = CanonicalEventV1(
        event_id=f"evt_{uuid.uuid4().hex[:12]}",
        trace_id=trace_id,
        span_id=span_id,
        parent_span_id=parent_span_id,
        run_id=run_id,
        agent_id=eff_agent_id,
        agent_name=eff_agent_name,
        team=eff_team,
        framework="custom",
        attempt_number=attempt_number,
        span_type=SpanType.TOOL,
        operation_name=tool_name,
        status=SpanStatus.AWAITING_APPROVAL,
        started_at=started_at,
        ended_at=None,
        model=None,
        usage=None,
        attributes={"inputs": inputs},
    )
    get_exporter().enqueue(awaiting_event)

    # b) Flush immediately so span is persisted in DB before requesting approval
    get_exporter().flush(timeout=5.0)

    base_url, api_key = _resolve_sentinel_config()
    headers = {
        "Content-Type": "application/json",
        "X-API-Key": api_key,
    }
    req_payload = {
        "run_id": run_id,
        "span_id": span_id,
        "agent_id": eff_agent_id,
        "tool_name": tool_name,
        "sanitized_args": inputs,
        "risk_level": risk_level,
        "policy_reason": policy_reason,
    }

    prev_span_id = parent_span_id
    set_current_span_id(span_id)

    try:
        # c) POST to {SENTINEL_URL}/api/approvals/request
        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.post(
                    f"{base_url}/api/approvals/request",
                    json=req_payload,
                    headers=headers,
                )
                resp.raise_for_status()
                approval_data = resp.json()
                approval_id = approval_data["approval_id"]
        except httpx.HTTPError as exc:
            ended_at = datetime.now(UTC)
            error_info = ErrorInfo(
                error_class=type(exc).__name__,
                message=f"Failed to submit approval request: {exc}",
                stack_summary=traceback.format_exc(),
            )
            fail_event = CanonicalEventV1(
                event_id=f"evt_{uuid.uuid4().hex[:12]}",
                trace_id=trace_id,
                span_id=span_id,
                parent_span_id=parent_span_id,
                run_id=run_id,
                agent_id=eff_agent_id,
                agent_name=eff_agent_name,
                team=eff_team,
                framework="custom",
                attempt_number=attempt_number,
                span_type=SpanType.TOOL,
                operation_name=tool_name,
                status=SpanStatus.FAILED,
                started_at=started_at,
                ended_at=ended_at,
                model=None,
                usage=None,
                error=error_info,
                attributes={"inputs": inputs},
            )
            get_exporter().enqueue(fail_event)
            get_exporter().flush(timeout=5.0)
            raise SentinelGovernanceError(
                f"Failed to submit approval request for tool '{tool_name}': {exc}"
            ) from exc

        # d) Poll GET {SENTINEL_URL}/api/approvals/{approval_id}/wait?timeout=20
        start_poll = time.monotonic()
        decision_status: str | None = None
        decision_data: dict[str, Any] = {}

        with httpx.Client(timeout=30.0) as client:
            while True:
                elapsed = time.monotonic() - start_poll
                remaining = timeout_seconds - elapsed
                if remaining <= 0:
                    break
                wait_timeout = min(20, max(1, int(remaining)))
                try:
                    poll_resp = client.get(
                        f"{base_url}/api/approvals/{approval_id}/wait?timeout={wait_timeout}",
                        headers=headers,
                        timeout=float(wait_timeout + 5),
                    )
                    if poll_resp.is_success:
                        decision_data = poll_resp.json()
                        current_status = decision_data.get("status")
                        if current_status in ("APPROVED", "REJECTED"):
                            decision_status = current_status
                            break
                except httpx.TimeoutException:
                    pass
                except httpx.HTTPError:
                    time.sleep(0.5)

        # e) If APPROVED:
        if decision_status == "APPROVED":
            running_event = CanonicalEventV1(
                event_id=f"evt_{uuid.uuid4().hex[:12]}",
                trace_id=trace_id,
                span_id=span_id,
                parent_span_id=parent_span_id,
                run_id=run_id,
                agent_id=eff_agent_id,
                agent_name=eff_agent_name,
                team=eff_team,
                framework="custom",
                attempt_number=attempt_number,
                span_type=SpanType.TOOL,
                operation_name=tool_name,
                status=SpanStatus.RUNNING,
                started_at=started_at,
                ended_at=None,
                model=None,
                usage=None,
                attributes={"inputs": inputs},
            )
            get_exporter().enqueue(running_event)

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
                    framework="custom",
                    attempt_number=attempt_number,
                    span_type=SpanType.TOOL,
                    operation_name=tool_name,
                    status=SpanStatus.SUCCEEDED,
                    started_at=started_at,
                    ended_at=ended_at,
                    model=None,
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
                fail_event = CanonicalEventV1(
                    event_id=f"evt_{uuid.uuid4().hex[:12]}",
                    trace_id=trace_id,
                    span_id=span_id,
                    parent_span_id=parent_span_id,
                    run_id=run_id,
                    agent_id=eff_agent_id,
                    agent_name=eff_agent_name,
                    team=eff_team,
                    framework="custom",
                    attempt_number=attempt_number,
                    span_type=SpanType.TOOL,
                    operation_name=tool_name,
                    status=SpanStatus.FAILED,
                    started_at=started_at,
                    ended_at=ended_at,
                    model=None,
                    usage=None,
                    error=error_info,
                    attributes={"inputs": inputs},
                )
                get_exporter().enqueue(fail_event)
                raise

        # f) If REJECTED:
        elif decision_status == "REJECTED":
            ended_at = datetime.now(UTC)
            rejection_comment = (
                decision_data.get("comment")
                or "Tool execution rejected by human approver"
            )
            error_info = ErrorInfo(
                error_class="GovernanceRejectedError",
                message=f"Tool execution '{tool_name}' was rejected: {rejection_comment}",
            )
            attributes = {
                "inputs": inputs,
                "rejection": {
                    "decided_by": decision_data.get("decided_by"),
                    "comment": decision_data.get("comment"),
                },
            }
            cancelled_event = CanonicalEventV1(
                event_id=f"evt_{uuid.uuid4().hex[:12]}",
                trace_id=trace_id,
                span_id=span_id,
                parent_span_id=parent_span_id,
                run_id=run_id,
                agent_id=eff_agent_id,
                agent_name=eff_agent_name,
                team=eff_team,
                framework="custom",
                attempt_number=attempt_number,
                span_type=SpanType.TOOL,
                operation_name=tool_name,
                status=SpanStatus.CANCELLED,
                started_at=started_at,
                ended_at=ended_at,
                model=None,
                usage=None,
                error=error_info,
                attributes=attributes,
            )
            get_exporter().enqueue(cancelled_event)
            get_exporter().flush(timeout=5.0)
            raise GovernanceRejectedError(
                f"Tool execution '{tool_name}' was rejected by human approver: {rejection_comment}"
            )

        # Timed out:
        else:
            ended_at = datetime.now(UTC)
            error_info = ErrorInfo(
                error_class="GovernanceTimeoutError",
                message=(
                    f"Tool execution '{tool_name}' timed out after "
                    f"{timeout_seconds}s waiting for human approval"
                ),
            )
            timed_out_event = CanonicalEventV1(
                event_id=f"evt_{uuid.uuid4().hex[:12]}",
                trace_id=trace_id,
                span_id=span_id,
                parent_span_id=parent_span_id,
                run_id=run_id,
                agent_id=eff_agent_id,
                agent_name=eff_agent_name,
                team=eff_team,
                framework="custom",
                attempt_number=attempt_number,
                span_type=SpanType.TOOL,
                operation_name=tool_name,
                status=SpanStatus.TIMED_OUT,
                started_at=started_at,
                ended_at=ended_at,
                model=None,
                usage=None,
                error=error_info,
                attributes={"inputs": inputs},
            )
            get_exporter().enqueue(timed_out_event)
            get_exporter().flush(timeout=5.0)
            raise GovernanceTimeoutError(
                f"Tool execution '{tool_name}' timed out after {timeout_seconds}s waiting for human approval"
            )
    finally:
        set_current_span_id(prev_span_id)


def _gate_tool_wrapper(
    fn: Callable[..., Any],
    tool_name: str,
    risk_level: str,
    policy_reason: str,
    timeout_seconds: int,
) -> Callable[..., Any]:
    if inspect.iscoroutinefunction(fn):

        @functools.wraps(fn)
        async def async_gate_wrapper(*args: Any, **kwargs: Any) -> Any:
            return await _execute_async_gate(
                fn=fn,
                tool_name=tool_name,
                risk_level=risk_level,
                policy_reason=policy_reason,
                timeout_seconds=timeout_seconds,
                args=args,
                kwargs=kwargs,
            )

        return async_gate_wrapper

    @functools.wraps(fn)
    def sync_gate_wrapper(*args: Any, **kwargs: Any) -> Any:
        return _execute_sync_gate(
            fn=fn,
            tool_name=tool_name,
            risk_level=risk_level,
            policy_reason=policy_reason,
            timeout_seconds=timeout_seconds,
            args=args,
            kwargs=kwargs,
        )

    return sync_gate_wrapper


def gate_tool(
    tool_name: str | Callable[..., Any] | None = None,
    risk_level: str = "HIGH",
    policy_reason: str = "Protected tool execution requires human approval",
    timeout_seconds: int = 120,
) -> Any:
    """Decorator for synchronous Human-in-the-Loop pre-execution approval gate.

    Emits an AWAITING_APPROVAL span, flushes immediately to Sentinel backend,
    requests approval, and polls until APPROVED, REJECTED, or timed out.
    """
    if callable(tool_name):
        fn = tool_name
        return _gate_tool_wrapper(
            fn=fn,
            tool_name=fn.__name__,
            risk_level=risk_level,
            policy_reason=policy_reason,
            timeout_seconds=timeout_seconds,
        )

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        op_name = (
            tool_name if isinstance(tool_name, str) and tool_name else fn.__name__
        )
        return _gate_tool_wrapper(
            fn=fn,
            tool_name=op_name,
            risk_level=risk_level,
            policy_reason=policy_reason,
            timeout_seconds=timeout_seconds,
        )

    return decorator


__all__ = [
    "_check_runtime_control",
    "gate_tool",
    "trace_agent",
    "trace_llm",
    "trace_tool",
]

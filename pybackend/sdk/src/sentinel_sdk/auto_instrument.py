import contextlib
import logging
import os
import traceback
from contextvars import ContextVar, Token
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import wrapt

from sentinel_sdk.context import (
    current_agent_id_var,
    current_agent_name_var,
    current_span_id_var,
    current_trace_id_var,
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
    set_trace_id,
)
from sentinel_sdk.decorators import _CONTROL_CACHE, _check_runtime_control
from sentinel_sdk.exceptions import BudgetCircuitBreakerError, RunCancelledError
from sentinel_sdk.exporter import SentinelExporter, configure_sentinel, get_exporter
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

_is_instrumented: bool = False
_langchain_patched: bool = False
_default_agent_id: str = "auto-instrumented-agent"
_default_framework: str = "auto-instrumented"

_PROVIDER_RULES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("groq.com",), "groq"),
    (("generativelanguage.googleapis.com",), "google"),
    (("11434", "ollama"), "ollama"),
    (("huggingface.co",), "huggingface"),
)


def _infer_provider(client_instance: Any) -> str:
    """Infer model provider from the wrapped OpenAI-compatible client's base_url."""
    base_url = str(
        getattr(getattr(client_instance, "_client", None), "base_url", "")
    ).lower()
    for patterns, provider in _PROVIDER_RULES:
        if any(pattern in base_url for pattern in patterns):
            return provider
    return "openai"


def _extract_usage(response: Any) -> TokenUsage | None:
    """Extract TokenUsage from an OpenAI response object, or return None if absent."""
    usage = getattr(response, "usage", None)
    if usage is None:
        return None

    if isinstance(usage, dict):
        in_tok = usage.get("prompt_tokens", usage.get("input_tokens"))
        out_tok = usage.get("completion_tokens", usage.get("output_tokens"))
    else:
        in_tok = getattr(
            usage, "prompt_tokens", getattr(usage, "input_tokens", None)
        )
        out_tok = getattr(
            usage, "completion_tokens", getattr(usage, "output_tokens", None)
        )

    try:
        in_val = int(in_tok) if in_tok is not None else None
    except (ValueError, TypeError):
        in_val = None

    try:
        out_val = int(out_tok) if out_tok is not None else None
    except (ValueError, TypeError):
        out_val = None

    if in_val is None and out_val is None:
        return None
    return TokenUsage(input_tokens=in_val, output_tokens=out_val)


def _extract_output_preview(response: Any) -> Any:
    """Extract and redact assistant message content from a chat completion response."""
    choices = getattr(response, "choices", None)
    if isinstance(choices, list) and choices:
        first = choices[0]
        message = getattr(first, "message", None)
        if message is not None:
            content = getattr(message, "content", None)
            tool_calls = getattr(message, "tool_calls", None)
            preview: dict[str, Any] = {}
            if content is not None:
                preview["content"] = content
            if tool_calls:
                preview["tool_calls"] = tool_calls
            if preview:
                return redact_payload(preview)
    if isinstance(response, dict):
        return redact_payload(response)
    return redact_payload(str(response)) if response is not None else None


@dataclass
class _InvocationContext:
    exporter: SentinelExporter
    auto_run: bool
    run_id: str
    trace_id: str
    team: str
    agent_id: str
    agent_name: str
    root_span_id: str | None
    root_started_at: datetime | None
    root_attempt: int
    llm_span_id: str
    parent_span_id: str | None
    llm_started_at: datetime
    llm_attempt: int
    operation_name: str
    model_info: ModelInfo
    base_attributes: dict[str, Any]
    context_tokens: list[tuple[ContextVar[Any], Token[Any]]]


def _reset_context_tokens(tokens: list[tuple[ContextVar[Any], Token[Any]]]) -> None:
    for var, token in reversed(tokens):
        var.reset(token)


def _begin_openai_invocation(
    instance: Any,
    kwargs: dict[str, Any],
) -> _InvocationContext:
    exporter = get_exporter()
    existing_run_id = get_run_id()
    auto_run = existing_run_id is None
    needs_agent_span = auto_run or (get_current_span_id() is None)
    now = datetime.now(UTC)

    agent_id = get_agent_id() or _default_agent_id
    agent_name = get_agent_name() or agent_id
    team = get_team()
    model_name = str(kwargs.get("model", "unknown"))
    provider = _infer_provider(instance)
    model_info = ModelInfo(provider=provider, name=model_name)
    operation_name = f"chat.completions:{model_name}"
    prompt_preview = redact_payload(kwargs.get("messages", []))
    base_attributes: dict[str, Any] = {
        "inputs": {
            "model": model_name,
            "messages": prompt_preview,
        }
    }

    context_tokens: list[tuple[ContextVar[Any], Token[Any]]] = []
    root_span_id: str | None = None
    root_started_at: datetime | None = None
    root_attempt = 1

    if needs_agent_span:
        run_id = (
            f"run_auto_{uuid4().hex[:12]}"
            if auto_run
            else str(existing_run_id)
        )
        trace_id = uuid4().hex if auto_run else (get_trace_id() or uuid4().hex)
        root_span_id = f"span_{uuid4().hex[:12]}"
        root_started_at = now
        root_attempt = next_attempt_number(run_id, agent_id, _default_agent_id)

        if auto_run:
            from sentinel_sdk.context import current_run_id_var

            context_tokens = [
                (current_trace_id_var, set_trace_id(trace_id)),
                (current_span_id_var, set_current_span_id(root_span_id)),
                (current_agent_id_var, set_agent_id(agent_id)),
                (current_agent_name_var, set_agent_name(agent_name)),
                (current_run_id_var, set_run_id(run_id)),
            ]
        else:
            context_tokens = [
                (current_span_id_var, set_current_span_id(root_span_id)),
                (current_agent_id_var, set_agent_id(agent_id)),
                (current_agent_name_var, set_agent_name(agent_name)),
            ]

        exporter.enqueue(
            CanonicalEventV1(
                event_id=f"evt_{uuid4().hex[:12]}",
                trace_id=trace_id,
                span_id=root_span_id,
                parent_span_id=None,
                run_id=run_id,
                agent_id=agent_id,
                agent_name=agent_name,
                team=team,
                framework=_default_framework,
                attempt_number=root_attempt,
                span_type=SpanType.AGENT,
                operation_name=_default_agent_id,
                status=SpanStatus.RUNNING,
                started_at=root_started_at,
                ended_at=None,
                attributes={"auto_instrumented": True},
            )
        )
        parent_span_id: str | None = root_span_id
    else:
        run_id = str(existing_run_id)
        trace_id = get_trace_id() or uuid4().hex
        parent_span_id = get_current_span_id()

    llm_span_id = f"span_{uuid4().hex[:12]}"
    llm_started_at = datetime.now(UTC)
    llm_attempt = next_attempt_number(run_id, agent_id, operation_name)

    exporter.enqueue(
        CanonicalEventV1(
            event_id=f"evt_{uuid4().hex[:12]}",
            trace_id=trace_id,
            span_id=llm_span_id,
            parent_span_id=parent_span_id,
            run_id=run_id,
            agent_id=agent_id,
            agent_name=agent_name,
            team=team,
            framework=_default_framework,
            attempt_number=llm_attempt,
            span_type=SpanType.LLM,
            operation_name=operation_name,
            status=SpanStatus.RUNNING,
            started_at=llm_started_at,
            ended_at=None,
            model=model_info,
            usage=None,
            attributes=base_attributes,
        )
    )

    ctx = _InvocationContext(
        exporter=exporter,
        auto_run=auto_run,
        run_id=run_id,
        trace_id=trace_id,
        team=team,
        agent_id=agent_id,
        agent_name=agent_name,
        root_span_id=root_span_id,
        root_started_at=root_started_at,
        root_attempt=root_attempt,
        llm_span_id=llm_span_id,
        parent_span_id=parent_span_id,
        llm_started_at=llm_started_at,
        llm_attempt=llm_attempt,
        operation_name=operation_name,
        model_info=model_info,
        base_attributes=base_attributes,
        context_tokens=context_tokens,
    )

    try:
        ctrl = _check_runtime_control(run_id)
        if ctrl.get("cancelled"):
            _emit_cancelled_llm(
                ctx,
                error_class="RunCancelledError",
                message="Run aborted by operator kill-switch",
            )
            raise RunCancelledError("Run aborted by operator kill-switch")

        blocked_reason = ctrl.get("blocked_reason")
        if blocked_reason:
            msg = f"Blocked by policy: {blocked_reason}"
            _emit_cancelled_llm(
                ctx,
                error_class="BudgetCircuitBreakerError",
                message=msg,
            )
            raise BudgetCircuitBreakerError(msg)
    except (RunCancelledError, BudgetCircuitBreakerError) as exc:
        _close_root_span_on_error(ctx, exc, SpanStatus.CANCELLED)
        _reset_context_tokens(ctx.context_tokens)
        ctx.exporter.flush()
        _CONTROL_CACHE.pop(ctx.run_id, None)
        raise

    return ctx


def _emit_cancelled_llm(
    ctx: _InvocationContext,
    error_class: str,
    message: str,
) -> None:
    ctx.exporter.enqueue(
        CanonicalEventV1(
            event_id=f"evt_{uuid4().hex[:12]}",
            trace_id=ctx.trace_id,
            span_id=ctx.llm_span_id,
            parent_span_id=ctx.parent_span_id,
            run_id=ctx.run_id,
            agent_id=ctx.agent_id,
            agent_name=ctx.agent_name,
            team=ctx.team,
            framework=_default_framework,
            attempt_number=ctx.llm_attempt,
            span_type=SpanType.LLM,
            operation_name=ctx.operation_name,
            status=SpanStatus.CANCELLED,
            started_at=ctx.llm_started_at,
            ended_at=datetime.now(UTC),
            model=ctx.model_info,
            usage=None,
            error=ErrorInfo(error_class=error_class, message=message),
            attributes=ctx.base_attributes,
        )
    )


def _close_root_span_on_error(
    ctx: _InvocationContext,
    exc: BaseException,
    root_status: SpanStatus,
) -> None:
    if ctx.root_span_id is None:
        return
    ctx.exporter.enqueue(
        CanonicalEventV1(
            event_id=f"evt_{uuid4().hex[:12]}",
            trace_id=ctx.trace_id,
            span_id=ctx.root_span_id,
            parent_span_id=None,
            run_id=ctx.run_id,
            agent_id=ctx.agent_id,
            agent_name=ctx.agent_name,
            team=ctx.team,
            framework=_default_framework,
            attempt_number=ctx.root_attempt,
            span_type=SpanType.AGENT,
            operation_name=_default_agent_id,
            status=root_status,
            started_at=ctx.root_started_at or ctx.llm_started_at,
            ended_at=datetime.now(UTC),
            error=ErrorInfo(
                error_class=type(exc).__name__,
                message=str(exc),
                stack_summary=traceback.format_exc(),
            ),
            attributes={"auto_instrumented": True},
        )
    )


def _finish_openai_success(ctx: _InvocationContext, response: Any) -> None:
    ended_at = datetime.now(UTC)
    usage = _extract_usage(response)
    output_preview = _extract_output_preview(response)
    attrs = {**ctx.base_attributes, "output": output_preview}

    ctx.exporter.enqueue(
        CanonicalEventV1(
            event_id=f"evt_{uuid4().hex[:12]}",
            trace_id=ctx.trace_id,
            span_id=ctx.llm_span_id,
            parent_span_id=ctx.parent_span_id,
            run_id=ctx.run_id,
            agent_id=ctx.agent_id,
            agent_name=ctx.agent_name,
            team=ctx.team,
            framework=_default_framework,
            attempt_number=ctx.llm_attempt,
            span_type=SpanType.LLM,
            operation_name=ctx.operation_name,
            status=SpanStatus.SUCCEEDED,
            started_at=ctx.llm_started_at,
            ended_at=ended_at,
            model=ctx.model_info,
            usage=usage,
            attributes=attrs,
        )
    )

    if ctx.root_span_id is not None:
        ctx.exporter.enqueue(
            CanonicalEventV1(
                event_id=f"evt_{uuid4().hex[:12]}",
                trace_id=ctx.trace_id,
                span_id=ctx.root_span_id,
                parent_span_id=None,
                run_id=ctx.run_id,
                agent_id=ctx.agent_id,
                agent_name=ctx.agent_name,
                team=ctx.team,
                framework=_default_framework,
                attempt_number=ctx.root_attempt,
                span_type=SpanType.AGENT,
                operation_name=_default_agent_id,
                status=SpanStatus.SUCCEEDED,
                started_at=ctx.root_started_at or ctx.llm_started_at,
                ended_at=ended_at,
                attributes={"auto_instrumented": True},
            )
        )
        _reset_context_tokens(ctx.context_tokens)
        ctx.exporter.flush()
        _CONTROL_CACHE.pop(ctx.run_id, None)


def _finish_openai_error(ctx: _InvocationContext, exc: BaseException) -> None:
    ended_at = datetime.now(UTC)
    error_info = ErrorInfo(
        error_class=type(exc).__name__,
        message=str(exc),
        stack_summary=traceback.format_exc(),
    )
    ctx.exporter.enqueue(
        CanonicalEventV1(
            event_id=f"evt_{uuid4().hex[:12]}",
            trace_id=ctx.trace_id,
            span_id=ctx.llm_span_id,
            parent_span_id=ctx.parent_span_id,
            run_id=ctx.run_id,
            agent_id=ctx.agent_id,
            agent_name=ctx.agent_name,
            team=ctx.team,
            framework=_default_framework,
            attempt_number=ctx.llm_attempt,
            span_type=SpanType.LLM,
            operation_name=ctx.operation_name,
            status=SpanStatus.FAILED,
            started_at=ctx.llm_started_at,
            ended_at=ended_at,
            model=ctx.model_info,
            usage=None,
            error=error_info,
            attributes=ctx.base_attributes,
        )
    )
    if ctx.root_span_id is not None:
        _close_root_span_on_error(ctx, exc, SpanStatus.FAILED)
        _reset_context_tokens(ctx.context_tokens)
        ctx.exporter.flush()
        _CONTROL_CACHE.pop(ctx.run_id, None)


def _wrap_openai_create(
    wrapped: Any,
    instance: Any,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
) -> Any:
    """Synchronous wrapt wrapper for OpenAI chat.completions.create."""
    ctx = _begin_openai_invocation(instance, kwargs)
    try:
        response = wrapped(*args, **kwargs)
    except BaseException as exc:
        _finish_openai_error(ctx, exc)
        raise
    _finish_openai_success(ctx, response)
    return response


async def _wrap_openai_async_create(
    wrapped: Any,
    instance: Any,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
) -> Any:
    """Asynchronous wrapt wrapper for OpenAI AsyncCompletions.create."""
    ctx = _begin_openai_invocation(instance, kwargs)
    try:
        response = await wrapped(*args, **kwargs)
    except BaseException as exc:
        _finish_openai_error(ctx, exc)
        raise
    _finish_openai_success(ctx, response)
    return response


def _patch_langchain() -> None:
    """Optionally register a LangChain callback hook emitting TOOL spans."""
    global _langchain_patched
    if _langchain_patched:
        return

    try:
        from langchain_core.callbacks import BaseCallbackHandler
        from langchain_core.tracers.context import register_configure_hook
    except ImportError:
        return

    class SentinelLangChainCallback(BaseCallbackHandler):
        """Auto-injected LangChain callback handler emitting TOOL spans."""

        def __init__(self) -> None:
            super().__init__()
            self._spans: dict[UUID, dict[str, Any]] = {}

        def on_tool_start(
            self,
            serialized: dict[str, Any] | None,
            input_str: str,
            *,
            run_id: UUID,
            parent_run_id: UUID | None = None,
            inputs: dict[str, Any] | None = None,
            **kwargs: Any,
        ) -> Any:
            op_name = "Tool"
            if serialized:
                op_name = (
                    serialized.get("name")
                    or (serialized.get("id") or ["Tool"])[-1]
                )

            sentinel_run_id = get_run_id() or f"run_auto_{uuid4().hex[:12]}"
            sentinel_trace_id = get_trace_id() or uuid4().hex
            agent_id = get_agent_id() or _default_agent_id
            agent_name = get_agent_name() or agent_id
            team = get_team()
            parent_span_id = (
                f"span_{parent_run_id.hex[:12]}"
                if parent_run_id is not None
                else get_current_span_id()
            )
            span_id = f"span_{run_id.hex[:12]}"
            started_at = datetime.now(UTC)
            attempt = next_attempt_number(sentinel_run_id, agent_id, op_name)
            redacted_inputs = redact_payload(
                inputs if inputs is not None else {"input": input_str}
            )

            self._spans[run_id] = {
                "span_id": span_id,
                "parent_span_id": parent_span_id,
                "run_id": sentinel_run_id,
                "trace_id": sentinel_trace_id,
                "agent_id": agent_id,
                "agent_name": agent_name,
                "team": team,
                "attempt_number": attempt,
                "operation_name": op_name,
                "started_at": started_at,
                "inputs": redacted_inputs,
            }
            get_exporter().enqueue(
                CanonicalEventV1(
                    event_id=f"evt_{uuid4().hex[:12]}",
                    trace_id=sentinel_trace_id,
                    span_id=span_id,
                    parent_span_id=parent_span_id,
                    run_id=sentinel_run_id,
                    agent_id=agent_id,
                    agent_name=agent_name,
                    team=team,
                    framework=_default_framework,
                    attempt_number=attempt,
                    span_type=SpanType.TOOL,
                    operation_name=op_name,
                    status=SpanStatus.RUNNING,
                    started_at=started_at,
                    attributes={"inputs": redacted_inputs},
                )
            )

        def on_tool_end(
            self,
            output: Any,
            *,
            run_id: UUID,
            **kwargs: Any,
        ) -> Any:
            data = self._spans.pop(run_id, None)
            if data is None:
                return
            get_exporter().enqueue(
                CanonicalEventV1(
                    event_id=f"evt_{uuid4().hex[:12]}",
                    trace_id=data["trace_id"],
                    span_id=data["span_id"],
                    parent_span_id=data["parent_span_id"],
                    run_id=data["run_id"],
                    agent_id=data["agent_id"],
                    agent_name=data["agent_name"],
                    team=data["team"],
                    framework=_default_framework,
                    attempt_number=data["attempt_number"],
                    span_type=SpanType.TOOL,
                    operation_name=data["operation_name"],
                    status=SpanStatus.SUCCEEDED,
                    started_at=data["started_at"],
                    ended_at=datetime.now(UTC),
                    attributes={
                        "inputs": data["inputs"],
                        "output": redact_payload(output),
                    },
                )
            )

        def on_tool_error(
            self,
            error: BaseException,
            *,
            run_id: UUID,
            **kwargs: Any,
        ) -> Any:
            data = self._spans.pop(run_id, None)
            if data is None:
                return
            get_exporter().enqueue(
                CanonicalEventV1(
                    event_id=f"evt_{uuid4().hex[:12]}",
                    trace_id=data["trace_id"],
                    span_id=data["span_id"],
                    parent_span_id=data["parent_span_id"],
                    run_id=data["run_id"],
                    agent_id=data["agent_id"],
                    agent_name=data["agent_name"],
                    team=data["team"],
                    framework=_default_framework,
                    attempt_number=data["attempt_number"],
                    span_type=SpanType.TOOL,
                    operation_name=data["operation_name"],
                    status=SpanStatus.FAILED,
                    started_at=data["started_at"],
                    ended_at=datetime.now(UTC),
                    error=ErrorInfo(
                        error_class=type(error).__name__,
                        message=str(error),
                        stack_summary=traceback.format_exc(),
                    ),
                    attributes={"inputs": data["inputs"]},
                )
            )

    os.environ["SENTINEL_AUTO_INSTRUMENT"] = "true"
    cb_var: ContextVar[BaseCallbackHandler | None] = ContextVar(
        "sentinel_auto_langchain_cb",
        default=None,
    )
    register_configure_hook(
        cb_var,
        inheritable=True,
        handle_class=SentinelLangChainCallback,
        env_var="SENTINEL_AUTO_INSTRUMENT",
    )
    _langchain_patched = True


def instrument(
    api_key: str | None = None,
    base_url: str | None = None,
    agent_id: str = "auto-instrumented-agent",
    framework: str = "auto-instrumented",
) -> None:
    """Enable zero-code-change auto-instrumentation for OpenAI-compatible SDKs and LangChain."""
    global _is_instrumented, _default_agent_id, _default_framework

    if api_key is not None:
        os.environ["SENTINEL_API_KEY"] = api_key
    if base_url is not None:
        os.environ["SENTINEL_URL"] = base_url

    _default_agent_id = agent_id
    _default_framework = framework

    if api_key is not None or base_url is not None:
        with contextlib.suppress(ValueError):
            configure_sentinel(base_url=base_url, api_key=api_key)

    if _is_instrumented:
        return

    try:
        import openai.resources.chat.completions as completions_mod

        wrapt.wrap_function_wrapper(
            completions_mod, "Completions.create", _wrap_openai_create
        )
        wrapt.wrap_function_wrapper(
            completions_mod,
            "AsyncCompletions.create",
            _wrap_openai_async_create,
        )
    except ImportError:
        logger.debug("openai package not installed; skipping OpenAI auto-instrumentation")

    _patch_langchain()
    _is_instrumented = True


__all__ = [
    "_extract_usage",
    "_infer_provider",
    "_patch_langchain",
    "_wrap_openai_async_create",
    "_wrap_openai_create",
    "instrument",
]

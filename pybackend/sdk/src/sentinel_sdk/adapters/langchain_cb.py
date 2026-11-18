import threading
import traceback
import uuid
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from langchain_core.callbacks.base import BaseCallbackHandler
from langchain_core.outputs import LLMResult

from sentinel_sdk.context import (
    get_agent_id,
    get_agent_name,
    get_current_span_id,
    get_run_id,
    get_team,
    get_trace_id,
    next_attempt_number,
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


class SentinelLangChainCallback(BaseCallbackHandler):
    """LangChain callback handler streaming telemetry events to Sentinel control tower."""

    def __init__(
        self,
        agent_id: str | None = None,
        agent_name: str | None = None,
        team: str | None = None,
        run_id: str | None = None,
        trace_id: str | None = None,
    ) -> None:
        super().__init__()
        self.agent_id = agent_id
        self.agent_name = agent_name
        self.team = team
        self.run_id = run_id
        self.trace_id = trace_id
        self._lock = threading.Lock()
        self._spans: dict[UUID, dict[str, Any]] = {}

    def _start_span(
        self,
        run_id: UUID,
        parent_run_id: UUID | None,
        span_type: SpanType,
        operation_name: str,
        inputs: Any,
        model_info: ModelInfo | None = None,
    ) -> None:
        span_id = f"span_{run_id.hex[:12]}"
        parent_span_id = (
            f"span_{parent_run_id.hex[:12]}"
            if parent_run_id is not None
            else get_current_span_id()
        )
        started_at = datetime.now(UTC)

        sentinel_run_id = (
            self.run_id or get_run_id() or f"run_{uuid.uuid4().hex[:12]}"
        )
        sentinel_trace_id = self.trace_id or get_trace_id() or uuid.uuid4().hex
        sentinel_agent_id = (
            self.agent_id or get_agent_id() or "langchain-agent"
        )
        sentinel_agent_name = (
            self.agent_name or get_agent_name() or "LangChain Agent"
        )
        sentinel_team = self.team or get_team()

        attempt_number = next_attempt_number(
            sentinel_run_id, sentinel_agent_id, operation_name
        )
        redacted_inputs = redact_payload(inputs)

        span_data = {
            "span_id": span_id,
            "parent_span_id": parent_span_id,
            "run_id": sentinel_run_id,
            "trace_id": sentinel_trace_id,
            "agent_id": sentinel_agent_id,
            "agent_name": sentinel_agent_name,
            "team": sentinel_team,
            "framework": "langchain",
            "attempt_number": attempt_number,
            "span_type": span_type,
            "operation_name": operation_name,
            "started_at": started_at,
            "model_info": model_info,
            "inputs": redacted_inputs,
        }
        with self._lock:
            self._spans[run_id] = span_data

        event = CanonicalEventV1(
            event_id=f"evt_{uuid.uuid4().hex[:12]}",
            trace_id=sentinel_trace_id,
            span_id=span_id,
            parent_span_id=parent_span_id,
            run_id=sentinel_run_id,
            agent_id=sentinel_agent_id,
            agent_name=sentinel_agent_name,
            team=sentinel_team,
            framework="langchain",
            attempt_number=attempt_number,
            span_type=span_type,
            operation_name=operation_name,
            status=SpanStatus.RUNNING,
            started_at=started_at,
            ended_at=None,
            model=model_info,
            usage=None,
            attributes={"inputs": redacted_inputs},
        )
        get_exporter().enqueue(event)

    def _end_span(
        self,
        run_id: UUID,
        output: Any,
        token_usage: TokenUsage | None = None,
    ) -> None:
        with self._lock:
            data = self._spans.pop(run_id, None)

        ended_at = datetime.now(UTC)
        if data is None:
            return

        redacted_output = redact_payload(output)
        attributes = {
            "inputs": data["inputs"],
            "output": redacted_output,
        }
        event = CanonicalEventV1(
            event_id=f"evt_{uuid.uuid4().hex[:12]}",
            trace_id=data["trace_id"],
            span_id=data["span_id"],
            parent_span_id=data["parent_span_id"],
            run_id=data["run_id"],
            agent_id=data["agent_id"],
            agent_name=data["agent_name"],
            team=data["team"],
            framework=data["framework"],
            attempt_number=data["attempt_number"],
            span_type=data["span_type"],
            operation_name=data["operation_name"],
            status=SpanStatus.SUCCEEDED,
            started_at=data["started_at"],
            ended_at=ended_at,
            model=data["model_info"],
            usage=token_usage,
            attributes=attributes,
        )
        get_exporter().enqueue(event)

    def _error_span(
        self,
        run_id: UUID,
        error: BaseException,
    ) -> None:
        with self._lock:
            data = self._spans.pop(run_id, None)

        ended_at = datetime.now(UTC)
        if data is None:
            return

        error_info = ErrorInfo(
            error_class=type(error).__name__,
            message=str(error),
            stack_summary=traceback.format_exc(),
        )
        event = CanonicalEventV1(
            event_id=f"evt_{uuid.uuid4().hex[:12]}",
            trace_id=data["trace_id"],
            span_id=data["span_id"],
            parent_span_id=data["parent_span_id"],
            run_id=data["run_id"],
            agent_id=data["agent_id"],
            agent_name=data["agent_name"],
            team=data["team"],
            framework=data["framework"],
            attempt_number=data["attempt_number"],
            span_type=data["span_type"],
            operation_name=data["operation_name"],
            status=SpanStatus.FAILED,
            started_at=data["started_at"],
            ended_at=ended_at,
            model=data["model_info"],
            usage=None,
            error=error_info,
            attributes={"inputs": data["inputs"]},
        )
        get_exporter().enqueue(event)

    # Chain Callbacks
    def on_chain_start(
        self,
        serialized: dict[str, Any] | None,
        inputs: dict[str, Any],
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Any:
        op_name = "Chain"
        if serialized:
            op_name = (
                serialized.get("name")
                or (serialized.get("id") or ["Chain"])[-1]
            )
        self._start_span(
            run_id=run_id,
            parent_run_id=parent_run_id,
            span_type=SpanType.AGENT,
            operation_name=op_name,
            inputs=inputs,
        )

    def on_chain_end(
        self,
        outputs: dict[str, Any],
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> Any:
        self._end_span(run_id=run_id, output=outputs)

    def on_chain_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> Any:
        self._error_span(run_id=run_id, error=error)

    # LLM Callbacks
    def on_llm_start(
        self,
        serialized: dict[str, Any] | None,
        prompts: list[str],
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Any:
        op_name = "LLM"
        provider = "custom"
        model_name = "unknown"

        if metadata:
            provider = metadata.get("ls_provider") or metadata.get("provider") or provider
            model_name = metadata.get("model_name") or metadata.get("model") or model_name

        if serialized:
            op_name = (
                serialized.get("name")
                or (serialized.get("id") or ["LLM"])[-1]
            )
            kw = serialized.get("kwargs", {})
            if isinstance(kw, dict):
                model_name = kw.get("model_name") or kw.get("model") or model_name
                provider = kw.get("provider") or provider

        model_info = ModelInfo(provider=str(provider), name=str(model_name))
        self._start_span(
            run_id=run_id,
            parent_run_id=parent_run_id,
            span_type=SpanType.LLM,
            operation_name=op_name,
            inputs={"prompts": prompts},
            model_info=model_info,
        )

    def on_llm_end(
        self,
        response: LLMResult,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        **kwargs: Any,
    ) -> Any:
        token_usage: TokenUsage | None = None
        if response.llm_output and isinstance(response.llm_output, dict):
            raw_usage = response.llm_output.get("token_usage") or response.llm_output
            if isinstance(raw_usage, dict):
                in_tok = raw_usage.get("prompt_tokens", raw_usage.get("input_tokens"))
                out_tok = raw_usage.get(
                    "completion_tokens", raw_usage.get("output_tokens")
                )
                cached_tok = raw_usage.get("cached_tokens")
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
                    token_usage = TokenUsage(
                        input_tokens=in_val,
                        output_tokens=out_val,
                        cached_tokens=cached_val,
                    )

        generations = [
            [gen.text for gen in gen_list]
            for gen_list in response.generations
        ]
        self._end_span(
            run_id=run_id,
            output={"generations": generations, "llm_output": response.llm_output},
            token_usage=token_usage,
        )

    def on_llm_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        **kwargs: Any,
    ) -> Any:
        self._error_span(run_id=run_id, error=error)

    # Tool Callbacks
    def on_tool_start(
        self,
        serialized: dict[str, Any] | None,
        input_str: str,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        inputs: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Any:
        op_name = "Tool"
        if serialized:
            op_name = (
                serialized.get("name")
                or (serialized.get("id") or ["Tool"])[-1]
            )
        tool_inputs = inputs if inputs is not None else {"input": input_str}
        self._start_span(
            run_id=run_id,
            parent_run_id=parent_run_id,
            span_type=SpanType.TOOL,
            operation_name=op_name,
            inputs=tool_inputs,
        )

    def on_tool_end(
        self,
        output: Any,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> Any:
        self._end_span(run_id=run_id, output=output)

    def on_tool_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> Any:
        self._error_span(run_id=run_id, error=error)


__all__ = [
    "SentinelLangChainCallback",
]


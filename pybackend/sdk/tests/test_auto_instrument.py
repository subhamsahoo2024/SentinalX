from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import openai
import openai.resources.chat.completions as openai_completions
import pytest
from langchain_core.callbacks.manager import CallbackManager
from sentinel_sdk import (
    BudgetCircuitBreakerError,
    RunCancelledError,
    SentinelExporter,
    SpanStatus,
    SpanType,
    instrument,
    start_run,
)
from sentinel_sdk import auto_instrument as auto_mod
from sentinel_sdk.auto_instrument import (
    _extract_usage,
    _infer_provider,
    _patch_langchain,
    _wrap_openai_async_create,
    _wrap_openai_create,
)
from sentinel_sdk.context import current_span_id_var, get_run_id, set_current_span_id


@pytest.fixture
def mock_exporter():
    exporter = MagicMock(spec=SentinelExporter)
    exporter.enqueue = MagicMock()
    exporter.flush = MagicMock()
    with (
        patch.object(auto_mod, "get_exporter", return_value=exporter),
        patch.object(
            auto_mod,
            "_check_runtime_control",
            return_value={"cancelled": False, "blocked_reason": None},
        ),
    ):
        yield exporter


def test_infer_provider():
    def _client(url: str):
        return SimpleNamespace(_client=SimpleNamespace(base_url=url))

    assert _infer_provider(_client("https://api.groq.com/openai/v1")) == "groq"
    assert (
        _infer_provider(
            _client("https://generativelanguage.googleapis.com/v1beta/openai/")
        )
        == "google"
    )
    assert _infer_provider(_client("http://localhost:11434/v1")) == "ollama"
    assert _infer_provider(_client("https://ollama.internal/v1")) == "ollama"
    assert _infer_provider(_client("https://router.huggingface.co/v1")) == "huggingface"
    assert _infer_provider(_client("https://api.openai.com/v1")) == "openai"
    assert _infer_provider(SimpleNamespace()) == "openai"


def test_extract_usage():
    assert _extract_usage(SimpleNamespace(usage=None)) is None
    assert _extract_usage(SimpleNamespace()) is None

    usage_resp = SimpleNamespace(
        usage=SimpleNamespace(prompt_tokens=120, completion_tokens=45)
    )
    extracted = _extract_usage(usage_resp)
    assert extracted is not None
    assert extracted.input_tokens == 120
    assert extracted.output_tokens == 45


def test_sync_wrap_ephemeral_run_redaction_and_flush(mock_exporter):
    fake_instance = SimpleNamespace(
        _client=SimpleNamespace(base_url="https://api.groq.com/openai/v1")
    )
    fake_response = SimpleNamespace(
        usage=SimpleNamespace(prompt_tokens=50, completion_tokens=20),
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content="Summary complete", tool_calls=None)
            )
        ],
    )
    wrapped = MagicMock(return_value=fake_response)

    assert get_run_id() is None
    result = _wrap_openai_create(
        wrapped,
        fake_instance,
        (),
        {
            "model": "llama-3.3-70b-versatile",
            "messages": [{"role": "user", "content": "ok", "api_key": "secret-123"}],
        },
    )

    assert result is fake_response
    assert get_run_id() is None
    wrapped.assert_called_once()
    mock_exporter.flush.assert_called_once()

    events = [c.args[0] for c in mock_exporter.enqueue.call_args_list]
    assert len(events) == 4
    assert [e.span_type for e in events] == [
        SpanType.AGENT,
        SpanType.LLM,
        SpanType.LLM,
        SpanType.AGENT,
    ]
    assert [e.status for e in events] == [
        SpanStatus.RUNNING,
        SpanStatus.RUNNING,
        SpanStatus.SUCCEEDED,
        SpanStatus.SUCCEEDED,
    ]

    run_ids = {e.run_id for e in events}
    assert len(run_ids) == 1
    assert next(iter(run_ids)).startswith("run_auto_")

    llm_done = events[2]
    assert llm_done.parent_span_id == events[0].span_id
    assert llm_done.model is not None
    assert llm_done.model.provider == "groq"
    assert llm_done.model.name == "llama-3.3-70b-versatile"
    assert llm_done.usage is not None
    assert llm_done.usage.input_tokens == 50
    assert llm_done.usage.output_tokens == 20
    assert llm_done.attributes["inputs"]["messages"][0]["api_key"] == "[REDACTED]"
    assert llm_done.attributes["output"]["content"] == "Summary complete"


@pytest.mark.asyncio
async def test_async_wrap_inside_existing_run_and_error_handling(mock_exporter):
    fake_instance = SimpleNamespace(
        _client=SimpleNamespace(base_url="https://api.openai.com/v1")
    )

    async def ok_wrapped(*_args, **_kwargs):
        return SimpleNamespace(
            usage=None,
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content="Done", tool_calls=None)
                )
            ],
        )

    with start_run(run_id="run_existing_123", team="fraud-detection"):
        tok = set_current_span_id("span_outer_agent")
        try:
            await _wrap_openai_async_create(
                ok_wrapped,
                fake_instance,
                (),
                {"model": "gpt-4o", "messages": [{"role": "user", "content": "hi"}]},
            )
        finally:
            current_span_id_var.reset(tok)

    events = [c.args[0] for c in mock_exporter.enqueue.call_args_list]
    assert len(events) == 2
    assert all(e.run_id == "run_existing_123" for e in events)
    assert all(e.team == "fraud-detection" for e in events)
    assert all(e.span_type == SpanType.LLM for e in events)
    assert all(e.parent_span_id == "span_outer_agent" for e in events)
    assert events[1].usage is None

    # Error emission on exception
    mock_exporter.enqueue.reset_mock()

    async def failing_wrapped(*_args, **_kwargs):
        raise RuntimeError("Upstream 500")

    with pytest.raises(RuntimeError, match="Upstream 500"):
        await _wrap_openai_async_create(
            failing_wrapped,
            fake_instance,
            (),
            {"model": "gpt-4o", "messages": []},
        )

    err_events = [c.args[0] for c in mock_exporter.enqueue.call_args_list]
    assert err_events[2].span_type == SpanType.LLM
    assert err_events[2].status == SpanStatus.FAILED
    assert err_events[2].error is not None
    assert err_events[2].error.error_class == "RuntimeError"
    assert err_events[3].span_type == SpanType.AGENT
    assert err_events[3].status == SpanStatus.FAILED


def test_runtime_control_kill_switch_and_budget_breaker(mock_exporter):
    fake_instance = SimpleNamespace(
        _client=SimpleNamespace(base_url="https://api.openai.com/v1")
    )
    wrapped = MagicMock()

    with (
        patch.object(
            auto_mod,
            "_check_runtime_control",
            return_value={"cancelled": True, "blocked_reason": None},
        ),
        pytest.raises(RunCancelledError),
    ):
        _wrap_openai_create(
            wrapped,
            fake_instance,
            (),
            {"model": "gpt-4o", "messages": []},
        )
    wrapped.assert_not_called()
    assert mock_exporter.flush.called

    mock_exporter.enqueue.reset_mock()
    with (
        patch.object(
            auto_mod,
            "_check_runtime_control",
            return_value={"cancelled": False, "blocked_reason": "BUDGET_EXCEEDED"},
        ),
        pytest.raises(BudgetCircuitBreakerError),
    ):
        _wrap_openai_create(
            wrapped,
            fake_instance,
            (),
            {"model": "gpt-4o", "messages": []},
        )
    wrapped.assert_not_called()
    cancelled = [
        c.args[0]
        for c in mock_exporter.enqueue.call_args_list
        if c.args[0].status == SpanStatus.CANCELLED
    ]
    assert len(cancelled) == 2


def test_instrument_idempotent_and_langchain_hook(mock_exporter, monkeypatch):
    orig_sync = openai_completions.Completions.__dict__["create"]
    orig_async = openai_completions.AsyncCompletions.__dict__["create"]
    monkeypatch.setattr(auto_mod, "_is_instrumented", False)
    monkeypatch.setattr(auto_mod, "_langchain_patched", False)
    monkeypatch.delenv("SENTINEL_API_KEY", raising=False)
    monkeypatch.delenv("SENTINEL_URL", raising=False)
    monkeypatch.delenv("SENTINEL_AUTO_INSTRUMENT", raising=False)

    try:
        with patch.object(auto_mod, "configure_sentinel") as mock_cfg:
            instrument(
                api_key="sk_test_123",
                base_url="http://127.0.0.1:8000",
                agent_id="my-auto-agent",
                framework="auto-test",
            )
            mock_cfg.assert_called_once_with(
                base_url="http://127.0.0.1:8000",
                api_key="sk_test_123",
            )

        assert auto_mod._is_instrumented is True
        assert auto_mod._default_agent_id == "my-auto-agent"
        wrapped_sync = openai_completions.Completions.__dict__["create"]
        wrapped_async = openai_completions.AsyncCompletions.__dict__["create"]
        assert wrapped_sync is not orig_sync
        assert wrapped_async is not orig_async

        # Calling instrument() a second time must not double-wrap
        with patch.object(auto_mod.wrapt, "wrap_function_wrapper") as mock_wrap:
            instrument()
            mock_wrap.assert_not_called()
        assert openai_completions.Completions.__dict__["create"] is wrapped_sync
        assert openai_completions.AsyncCompletions.__dict__["create"] is wrapped_async

        # Verify LangChain configure hook injects tool callback and emits TOOL spans
        _patch_langchain()
        cm = CallbackManager.configure()
        sentinel_cbs = [
            h for h in cm.handlers if type(h).__name__ == "SentinelLangChainCallback"
        ]
        assert sentinel_cbs
        cb = sentinel_cbs[0]
        tool_run = uuid4()
        with start_run(run_id="run_lc_1", team="it-ops"):
            cb.on_tool_start(
                {"name": "lookup_order"},
                '{"order_id": "123"}',
                run_id=tool_run,
            )
            cb.on_tool_end({"status": "shipped"}, run_id=tool_run)

        events = [c.args[0] for c in mock_exporter.enqueue.call_args_list]
        assert len(events) == 2
        assert all(e.span_type == SpanType.TOOL for e in events)
        assert events[0].status == SpanStatus.RUNNING
        assert events[1].status == SpanStatus.SUCCEEDED
        assert events[0].run_id == "run_lc_1"
    finally:
        openai_completions.Completions.create = orig_sync
        openai_completions.AsyncCompletions.create = orig_async
        auto_mod._is_instrumented = False
        _ = openai  # keep reference explicit

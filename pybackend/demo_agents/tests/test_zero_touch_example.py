import ast
from pathlib import Path
from unittest.mock import patch

import openai.resources.chat.completions as openai_completions
import pytest
from sentinel_demo import zero_touch_example
from sentinel_sdk import (
    BudgetCircuitBreakerError,
    SpanStatus,
    SpanType,
    auto_instrument,
)
from sentinel_sdk.exporter import SentinelExporter


def test_zero_touch_example_has_no_trace_decorators():
    source_path = Path(zero_touch_example.__file__)
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    decorators = [
        dec
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        for dec in node.decorator_list
    ]
    assert decorators == []
    assert "sentinel_sdk.instrument(" in source


def test_zero_touch_example_offline_mock_mode(monkeypatch, capsys):
    orig_sync = openai_completions.Completions.__dict__["create"]
    orig_async = openai_completions.AsyncCompletions.__dict__["create"]
    monkeypatch.setattr(auto_instrument, "_is_instrumented", False)
    monkeypatch.setattr(auto_instrument, "_langchain_patched", False)
    monkeypatch.setenv("SENTINEL_LIVE_LLM", "false")
    monkeypatch.setenv("SENTINEL_API_KEY", "dev-secret-key")
    monkeypatch.setenv("SENTINEL_URL", "http://127.0.0.1:8000")

    captured_events = []
    orig_enqueue = SentinelExporter.enqueue

    def capture_enqueue(self, event):
        captured_events.append(event)
        return orig_enqueue(self, event)

    try:
        with (
            patch.object(SentinelExporter, "enqueue", capture_enqueue),
            patch.object(SentinelExporter, "_send_batch", return_value=None),
            patch.object(
                auto_instrument,
                "_check_runtime_control",
                return_value={"cancelled": False, "blocked_reason": None},
            ),
        ):
            zero_touch_example.main()
    finally:
        openai_completions.Completions.create = orig_sync
        openai_completions.AsyncCompletions.create = orig_async
        auto_instrument._is_instrumented = False

    stdout = capsys.readouterr().out
    assert "fraud-scoring-service" in stdout
    assert "OFFLINE LOCAL MOCK SERVER" in stdout

    # Two sequential calls in one run -> AGENT + LLM start/end per call
    assert len(captured_events) == 8
    assert len({e.run_id for e in captured_events}) == 1
    llm_succeeded = [
        e
        for e in captured_events
        if e.span_type == SpanType.LLM and e.status == SpanStatus.SUCCEEDED
    ]
    assert len(llm_succeeded) == 2
    assert all(e.agent_id == "fraud-scoring-service" for e in captured_events)
    assert all(e.usage is not None for e in llm_succeeded)
    assert llm_succeeded[0].usage.input_tokens == 420
    assert llm_succeeded[0].usage.output_tokens == 135

    # Verify sensitive message fields were redacted automatically
    first_messages = llm_succeeded[0].attributes["inputs"]["messages"]
    assert first_messages[1]["api_key"] == "[REDACTED]"
    assert first_messages[1]["ssn"] == "[REDACTED]"


def test_zero_touch_example_blocks_second_call_on_budget_circuit_breaker(monkeypatch):
    orig_sync = openai_completions.Completions.__dict__["create"]
    orig_async = openai_completions.AsyncCompletions.__dict__["create"]
    monkeypatch.setattr(auto_instrument, "_is_instrumented", False)
    monkeypatch.setattr(auto_instrument, "_langchain_patched", False)
    monkeypatch.setenv("SENTINEL_LIVE_LLM", "false")
    monkeypatch.setenv("SENTINEL_API_KEY", "sk_live_test_key")
    monkeypatch.setenv("SENTINEL_URL", "http://127.0.0.1:8000")

    control_calls = 0
    http_calls = 0
    orig_do_post = zero_touch_example._MockOpenAIHandler.do_POST

    def counted_do_post(self):
        nonlocal http_calls
        http_calls += 1
        return orig_do_post(self)

    def fake_control(_run_id: str):
        nonlocal control_calls
        control_calls += 1
        if control_calls == 1:
            return {"cancelled": False, "blocked_reason": None}
        return {"cancelled": False, "blocked_reason": "BUDGET_EXCEEDED"}

    try:
        with (
            patch.object(SentinelExporter, "_send_batch", return_value=None),
            patch.object(auto_instrument, "_check_runtime_control", side_effect=fake_control),
            patch.object(zero_touch_example._MockOpenAIHandler, "do_POST", counted_do_post),
            pytest.raises(BudgetCircuitBreakerError),
        ):
            zero_touch_example.main()
    finally:
        openai_completions.Completions.create = orig_sync
        openai_completions.AsyncCompletions.create = orig_async
        auto_instrument._is_instrumented = False

    assert control_calls == 2
    assert http_calls == 1

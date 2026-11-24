import ast
import os
from unittest.mock import MagicMock, patch

from sentinel_demo.mock_llm import (
    is_live_llm_enabled,
    live_llm_context,
    mock_llm_completion,
)
from sentinel_demo.otel_external_sample import emit_external_trace
from sentinel_sdk import get_exporter

# ==============================================================================
# 1. Tests for mock_llm live vs mock behavior
# ==============================================================================


def test_mock_llm_deterministic_when_live_disabled():
    with patch.dict(
        os.environ,
        {"SENTINEL_LIVE_LLM": "false", "OPENAI_API_KEY": "", "LLM_API_KEY": ""},
    ):
        token = live_llm_context.set(None)
        try:
            assert not is_live_llm_enabled()
            res = mock_llm_completion("Triage critical network outage", latency_ms=0)
            assert "Coordinator Triage Assessment" in res["content"]
            assert res["model"] == "gpt-4o"
            assert res["provider"] == "openai"
            assert res["usage"]["input_tokens"] > 0
            assert res["usage"]["output_tokens"] > 0
        finally:
            live_llm_context.reset(token)


def test_mock_llm_fallback_when_api_key_missing():
    with patch.dict(
        os.environ,
        {"SENTINEL_LIVE_LLM": "true", "OPENAI_API_KEY": "", "LLM_API_KEY": ""},
    ):
        token = live_llm_context.set(None)
        try:
            assert is_live_llm_enabled()
            res = mock_llm_completion("Diagnose cluster failure", latency_ms=0)
            # Falls back seamlessly to deterministic mock
            assert "Diagnostic Assessment" in res["content"]
            assert res["model"] == "gpt-4o"
        finally:
            live_llm_context.reset(token)


def test_mock_llm_live_mode_calls_openai():
    mock_response = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = "Real Live LLM reasoning: identified memory leak in node 4."
    mock_response.choices = [mock_choice]
    mock_response.model = "gpt-4o-2024-08-06"
    mock_usage = MagicMock()
    mock_usage.prompt_tokens = 42
    mock_usage.completion_tokens = 88
    mock_response.usage = mock_usage

    mock_client_instance = MagicMock()
    mock_client_instance.chat.completions.create.return_value = mock_response

    mock_openai_module = MagicMock()
    mock_openai_module.OpenAI.return_value = mock_client_instance

    with patch.dict(
        os.environ,
        {
            "SENTINEL_LIVE_LLM": "true",
            "OPENAI_API_KEY": "sk-test-live-key",
            "OPENAI_BASE_URL": "http://localhost:11434/v1",
            "LLM_API_KEY": "",
            "LLM_BASE_URL": "",
            "LLM_PROVIDER": "",
            "LLM_MODEL": "",
        },
    ), patch.dict("sys.modules", {"openai": mock_openai_module}):
        token = live_llm_context.set(None)
        try:
            emitted = []
            get_exporter().enqueue = lambda e: emitted.append(e)

            res = mock_llm_completion(
                prompt="Investigate authentication spike",
                model="gpt-4o",
            )

            mock_openai_module.OpenAI.assert_called_once_with(
                base_url="http://localhost:11434/v1",
                api_key="sk-test-live-key",
            )
            mock_client_instance.chat.completions.create.assert_called_once_with(
                model="gpt-4o",
                messages=[{"role": "user", "content": "Investigate authentication spike"}],
                max_tokens=200,
            )

            assert res["content"] == "Real Live LLM reasoning: identified memory leak in node 4."
            assert res["model"] == "gpt-4o-2024-08-06"
            assert res["usage"]["input_tokens"] == 42
            assert res["usage"]["output_tokens"] == 88

            # Check that @trace_llm captured the real token usage
            assert len(emitted) == 2
            end_span = emitted[1]
            assert end_span.usage.input_tokens == 42
            assert end_span.usage.output_tokens == 88
        finally:
            live_llm_context.reset(token)


def test_mock_llm_live_mode_multi_provider_groq():
    mock_response = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = "Groq Llama inference: Root cause is deadlock."
    mock_response.choices = [mock_choice]
    mock_response.model = "llama-3.3-70b-versatile"
    mock_usage = MagicMock()
    mock_usage.prompt_tokens = 512
    mock_usage.completion_tokens = 128
    mock_response.usage = mock_usage

    mock_client_instance = MagicMock()
    mock_client_instance.chat.completions.create.return_value = mock_response

    mock_openai_module = MagicMock()
    mock_openai_module.OpenAI.return_value = mock_client_instance

    with patch.dict(
        os.environ,
        {
            "SENTINEL_LIVE_LLM": "true",
            "LLM_PROVIDER": "groq",
            "LLM_BASE_URL": "https://api.groq.com/openai/v1",
            "LLM_API_KEY": "gsk_test123",
            "LLM_MODEL": "llama-3.3-70b-versatile",
        },
    ), patch.dict("sys.modules", {"openai": mock_openai_module}):
        token = live_llm_context.set(None)
        try:
            emitted = []
            get_exporter().enqueue = lambda e: emitted.append(e)

            res = mock_llm_completion("Analyze deadlock")

            mock_openai_module.OpenAI.assert_called_once_with(
                base_url="https://api.groq.com/openai/v1",
                api_key="gsk_test123",
            )
            mock_client_instance.chat.completions.create.assert_called_once_with(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": "Analyze deadlock"}],
                max_tokens=200,
            )

            assert res["provider"] == "groq"
            assert res["model"] == "llama-3.3-70b-versatile"

            # Verify emitted span records actual provider and model
            assert len(emitted) == 2
            end_span = emitted[1]
            assert end_span.model is not None
            assert end_span.model.provider == "groq"
            assert end_span.model.name == "llama-3.3-70b-versatile"
            assert end_span.usage.input_tokens == 512
            assert end_span.usage.output_tokens == 128
        finally:
            live_llm_context.reset(token)


def test_mock_llm_live_mode_ollama_missing_usage():
    mock_response = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = "Ollama local inference completion."
    mock_response.choices = [mock_choice]
    mock_response.model = "llama3.2"
    mock_response.usage = None  # Local Ollama may omit usage

    mock_client_instance = MagicMock()
    mock_client_instance.chat.completions.create.return_value = mock_response

    mock_openai_module = MagicMock()
    mock_openai_module.OpenAI.return_value = mock_client_instance

    with patch.dict(
        os.environ,
        {
            "SENTINEL_LIVE_LLM": "true",
            "LLM_PROVIDER": "ollama",
            "LLM_BASE_URL": "http://localhost:11434/v1",
            "LLM_API_KEY": "ollama",
            "LLM_MODEL": "llama3.2",
        },
    ), patch.dict("sys.modules", {"openai": mock_openai_module}):
        token = live_llm_context.set(None)
        try:
            emitted = []
            get_exporter().enqueue = lambda e: emitted.append(e)

            res = mock_llm_completion("Analyze logs")

            mock_openai_module.OpenAI.assert_called_once_with(
                base_url="http://localhost:11434/v1",
                api_key="ollama",
            )
            assert res["provider"] == "ollama"
            assert res["model"] == "llama3.2"
            assert res["usage"] is None

            # Verify emitted span records actual provider, model, and None usage
            assert len(emitted) == 2
            end_span = emitted[1]
            assert end_span.model is not None
            assert end_span.model.provider == "ollama"
            assert end_span.model.name == "llama3.2"
            assert end_span.usage is None
        finally:
            live_llm_context.reset(token)


def test_mock_llm_context_variable_support():
    token = live_llm_context.set(True)
    try:
        assert is_live_llm_enabled()
    finally:
        live_llm_context.reset(token)


# ==============================================================================
# 2. Test runner.py --live-llm flag
# ==============================================================================


def test_runner_live_llm_flag():
    import argparse

    from sentinel_demo.runner import main

    with patch("argparse.ArgumentParser.parse_args") as mock_parse, patch(
        "sentinel_demo.runner.run_coordinator_agent"
    ) as mock_agent, patch("sentinel_sdk.flush"):
        mock_parse.return_value = argparse.Namespace(
            scenario="normal",
            ticket_id="INC-TEST",
            description="Test ticket",
            team="it-ops",
            dashboard_host="http://localhost:3000",
            live_llm=True,
        )
        mock_agent.return_value = {"status": "RESOLVED"}

        with patch.dict(os.environ, {}, clear=False):
            if "SENTINEL_LIVE_LLM" in os.environ:
                del os.environ["SENTINEL_LIVE_LLM"]

            main()
            assert os.environ.get("SENTINEL_LIVE_LLM") == "true"


def test_runner_cli_args_deterministic_run_id_and_team():
    from unittest.mock import MagicMock

    from sentinel_demo.runner import main

    with patch("sentinel_demo.runner.start_run") as mock_start_run, patch(
        "sentinel_demo.runner.run_coordinator_agent"
    ) as mock_agent, patch("sentinel_sdk.flush") as mock_flush:
        mock_ctx = MagicMock()
        mock_ctx.run_id = "run_det_42"
        mock_ctx.trace_id = "trc_42"
        mock_start_run.return_value.__enter__.return_value = mock_ctx
        mock_agent.return_value = {"status": "RESOLVED"}

        with patch("sys.argv", ["runner.py", "--run-id", "run_det_42", "--team", "security-ops"]):
            main()

        mock_start_run.assert_called_once_with(run_id="run_det_42", team="security-ops")
        mock_flush.assert_called_once()


def test_runner_all_scenarios_pass_run_metadata_and_flush():
    from unittest.mock import MagicMock

    from sentinel_demo.runner import main

    scenarios = ["normal", "hitl", "loop", "budget", "cascade", "stall", "slow_loop"]

    for sc in scenarios:
        with patch("sentinel_demo.runner.start_run") as mock_start_run, patch(
            "sentinel_demo.runner.run_coordinator_agent"
        ) as mock_agent, patch("sentinel_sdk.flush") as mock_flush:
            mock_ctx = MagicMock()
            mock_ctx.run_id = f"run_{sc}_123"
            mock_ctx.trace_id = f"trc_{sc}_123"
            mock_start_run.return_value.__enter__.return_value = mock_ctx
            mock_agent.return_value = {"status": "RESOLVED"}

            with patch("sys.argv", ["runner.py", "--scenario", sc, "--run-id", f"run_{sc}_123", "--team", "custom-team"]):
                main()

            mock_start_run.assert_called_once_with(run_id=f"run_{sc}_123", team="custom-team")
            mock_flush.assert_called_once()


# ==============================================================================
# 3. Tests for otel_external_sample.py
# ==============================================================================


def test_otel_external_sample_zero_sdk_imports():
    """Ensure otel_external_sample.py has ZERO imports from sentinel_sdk."""
    sample_path = os.path.join(
        os.path.dirname(__file__), "..", "src", "sentinel_demo", "otel_external_sample.py"
    )
    with open(sample_path, "r", encoding="utf-8") as f:
        tree = ast.parse(f.read(), filename="otel_external_sample.py")

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert "sentinel" not in alias.name, f"Forbidden import found: {alias.name}"
        elif isinstance(node, ast.ImportFrom):
            assert node.module is not None
            assert "sentinel" not in node.module, f"Forbidden import found: {node.module}"


def test_emit_external_trace_execution():
    """Test emit_external_trace emits a correlated 3-level trace."""
    spans_captured = []

    class MockSpanExporter:
        def __init__(self, endpoint=None, headers=None):
            self.endpoint = endpoint
            self.headers = headers

        def export(self, spans):
            spans_captured.extend(spans)
            from opentelemetry.sdk.trace.export import SpanExportResult
            return SpanExportResult.SUCCESS

        def shutdown(self):
            pass

        def force_flush(self, timeout_millis=30000):
            return True

    with patch(
        "sentinel_demo.otel_external_sample.OTLPSpanExporter",
        side_effect=MockSpanExporter,
    ):
        trace_id, run_id = emit_external_trace(
            endpoint="http://localhost:8000/v1/traces",
            api_key="dev-secret-key",
        )

        assert len(trace_id) == 32
        assert run_id == f"run_otel_{trace_id[:12]}"
        assert len(spans_captured) == 3

        # Identify spans by name
        spans_by_name = {s.name: s for s in spans_captured}
        assert "triage_billing_dispute" in spans_by_name
        assert "chat gpt-4o-mini" in spans_by_name
        assert "lookup_invoice" in spans_by_name

        parent = spans_by_name["triage_billing_dispute"]
        llm = spans_by_name["chat gpt-4o-mini"]
        tool = spans_by_name["lookup_invoice"]

        # Check attributes
        assert parent.attributes["gen_ai.operation.name"] == "invoke_agent"
        assert parent.attributes["gen_ai.agent.name"] == "BillingSupportAgent"
        assert parent.attributes["gen_ai.agent.id"] == "agent_billing_otel"
        assert parent.parent is None

        assert llm.attributes["gen_ai.operation.name"] == "chat"
        assert llm.attributes["gen_ai.provider.name"] == "openai"
        assert llm.attributes["gen_ai.request.model"] == "gpt-4o-mini"
        assert llm.attributes["gen_ai.usage.input_tokens"] == 640
        assert llm.attributes["gen_ai.usage.output_tokens"] == 210
        assert llm.parent.span_id == parent.context.span_id

        assert tool.attributes["gen_ai.operation.name"] == "execute_tool"
        assert tool.attributes["gen_ai.tool.name"] == "lookup_invoice"
        assert tool.parent.span_id == llm.context.span_id

        # Verify all 3 share same trace_id
        assert format(parent.context.trace_id, "032x") == trace_id
        assert format(llm.context.trace_id, "032x") == trace_id
        assert format(tool.context.trace_id, "032x") == trace_id

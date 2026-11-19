import asyncio
import uuid
from dataclasses import dataclass
from unittest.mock import MagicMock

import pytest
from langchain_core.outputs import Generation, LLMResult
from pydantic import BaseModel
from sentinel_sdk import (
    CanonicalEventV1,
    SentinelExporter,
    SentinelLangChainCallback,
    SpanStatus,
    SpanType,
    configure_sentinel,
    flush,
    get_exporter,
    redact_payload,
    start_run,
    trace_agent,
    trace_llm,
    trace_tool,
)
from sentinel_sdk.context import (
    get_agent_id,
    get_agent_name,
    get_run_id,
    get_team,
    get_trace_id,
    next_attempt_number,
    reset_attempt_counters,
)


# ============================================================================
# 1. Redactor Tests
# ============================================================================
def test_redactor_sensitive_keys():
    data = {
        "user_token": "tok_123",
        "SECRET_KEY": "supersecret",
        "password": "pass",
        "user_passwd": "pw",
        "api_key": "key1",
        "my_apiKey": "key2",
        "authorization_header": "Bearer abc",
        "aws_credentials": "cred",
        "user_ssn": "000-00-0000",
        "private_key_pem": "-----BEGIN...",
        "public_data": "normal_val",
        "count": 42,
    }
    redacted = redact_payload(data)
    assert redacted["user_token"] == "[REDACTED]"
    assert redacted["SECRET_KEY"] == "[REDACTED]"
    assert redacted["password"] == "[REDACTED]"
    assert redacted["user_passwd"] == "[REDACTED]"
    assert redacted["api_key"] == "[REDACTED]"
    assert redacted["my_apiKey"] == "[REDACTED]"
    assert redacted["authorization_header"] == "[REDACTED]"
    assert redacted["aws_credentials"] == "[REDACTED]"
    assert redacted["user_ssn"] == "[REDACTED]"
    assert redacted["private_key_pem"] == "[REDACTED]"
    assert redacted["public_data"] == "normal_val"
    assert redacted["count"] == 42


def test_redactor_nested_structures():
    nested = {
        "list": [1, {"api_key": "nested_key"}, "safe"],
        "tuple": ("safe_str", {"password": "nested_pass"}),
        "safe_dict": {"field": "value"},
    }
    redacted = redact_payload(nested)
    assert redacted["list"][1]["api_key"] == "[REDACTED]"
    assert redacted["list"][0] == 1
    assert isinstance(redacted["tuple"], tuple)
    assert redacted["tuple"][1]["password"] == "[REDACTED]"
    assert redacted["safe_dict"]["field"] == "value"


def test_redactor_string_truncation():
    long_str = "x" * 2500
    redacted = redact_payload(long_str, max_str_len=100)
    assert len(redacted) == 100 + len("...[TRUNCATED]")
    assert redacted.startswith("x" * 100)
    assert redacted.endswith("...[TRUNCATED]")

    short_str = "hello"
    assert redact_payload(short_str, max_str_len=100) == "hello"


def test_redactor_circular_reference():
    d: dict = {"key": "val"}
    d["self"] = d
    redacted = redact_payload(d)
    assert redacted["key"] == "val"
    assert redacted["self"] == "[CIRCULAR]"


def test_redactor_pydantic_and_dataclass():
    class TestModel(BaseModel):
        api_key: str
        name: str

    @dataclass
    class TestDataclass:
        password: str
        score: int

    red_pydantic = redact_payload(TestModel(api_key="123", name="test"))
    assert red_pydantic == {"api_key": "[REDACTED]", "name": "test"}

    red_dc = redact_payload(TestDataclass(password="xyz", score=99))
    assert red_dc == {"password": "[REDACTED]", "score": 99}


# ============================================================================
# 2. Context Tests
# ============================================================================
def test_context_start_run_sync():
    assert get_run_id() is None
    assert get_trace_id() is None

    with start_run(team="security") as ctx:
        assert ctx.run_id.startswith("run_")
        assert len(ctx.trace_id) == 32
        assert ctx.team == "security"
        assert get_run_id() == ctx.run_id
        assert get_trace_id() == ctx.trace_id
        assert get_team() == "security"

    assert get_run_id() is None
    assert get_trace_id() is None


@pytest.mark.asyncio
async def test_context_start_run_async():
    async with start_run(run_id="run_custom123", trace_id="a" * 32, team="core") as ctx:
        assert ctx == "run_custom123"
        assert ctx["run_id"] == "run_custom123"
        assert ctx.trace_id == "a" * 32
        assert get_run_id() == "run_custom123"
        assert get_trace_id() == "a" * 32
        assert get_team() == "core"

    assert get_run_id() is None


def test_context_attempt_counter():
    reset_attempt_counters()
    run1 = "run_111"
    run2 = "run_222"
    agent = "agent_a"
    op = "query_db"

    assert next_attempt_number(run1, agent, op) == 1
    assert next_attempt_number(run1, agent, op) == 2
    assert next_attempt_number(run1, agent, op) == 3
    # Different run
    assert next_attempt_number(run2, agent, op) == 1
    # Different agent
    assert next_attempt_number(run1, "agent_b", op) == 1


# ============================================================================
# 3. Exporter Tests
# ============================================================================
def test_exporter_configuration_and_flush():
    exporter = configure_sentinel(
        base_url="http://test-sentinel:9000",
        api_key="test-secret",
        batch_size=10,
        flush_interval=0.1,
    )
    assert exporter.base_url == "http://test-sentinel:9000"
    assert exporter.api_key == "test-secret"
    assert get_exporter() is exporter

    flush()


def test_exporter_batch_send():
    exporter = SentinelExporter(base_url="http://mock-api:8000", api_key="dev-key")
    mock_post = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 202
    mock_post.return_value = mock_resp
    exporter._client.post = mock_post

    dummy_event = CanonicalEventV1(
        event_id="evt_123",
        trace_id="t" * 32,
        span_id="span_123",
        run_id="run_123",
        agent_id="agent_x",
        span_type=SpanType.AGENT,
        operation_name="test_op",
        status=SpanStatus.RUNNING,
        started_at=asyncio.run(asyncio.sleep(0, result=None)) or __import__("datetime").datetime.now(__import__("datetime").UTC),
    )
    exporter.enqueue(dummy_event)
    exporter.flush()

    assert mock_post.called
    args, kwargs = mock_post.call_args
    assert args[0] == "http://mock-api:8000/api/telemetry/events"
    assert kwargs["headers"]["X-API-Key"] == "dev-key"
    assert len(kwargs["json"]["events"]) == 1
    assert kwargs["json"]["events"][0]["event_id"] == "evt_123"
    exporter.shutdown()


# ============================================================================
# 4. Decorators Tests
# ============================================================================
def test_decorators_sync_and_async():
    emitted: list[CanonicalEventV1] = []
    exporter = get_exporter()
    exporter.enqueue = lambda e: emitted.append(e)

    @trace_tool(tool_name="web_search")
    def search(query: str, api_key: str) -> dict:
        return {"result": f"found for {query}"}

    @trace_llm(provider="openai", model="gpt-4o")
    async def chat(prompt: str) -> dict:
        return {
            "reply": f"response to {prompt}",
            "usage": {"input_tokens": 50, "output_tokens": 100},
        }

    @trace_agent(agent_id="researcher-1", name="Research Agent", team="intel")
    async def run_agent(topic: str):
        assert get_agent_id() == "researcher-1"
        assert get_agent_name() == "Research Agent"
        assert get_team() == "intel"

        s_res = search(topic, api_key="secret123")
        c_res = await chat(s_res["result"])
        return c_res

    with start_run(team="intel") as run:
        assert run.team == "intel"
        result = asyncio.run(run_agent("AI Agents"))
        assert result["reply"] == "response to found for AI Agents"

    # Should have 6 events: (agent RUNNING, tool RUNNING, tool SUCCEEDED, llm RUNNING, llm SUCCEEDED, agent SUCCEEDED)
    assert len(emitted) == 6

    agent_start, tool_start, tool_end, llm_start, llm_end, agent_end = emitted

    # Hierarchy verification
    assert agent_start.span_type == SpanType.AGENT
    assert agent_start.operation_name == "run_agent"
    assert agent_start.parent_span_id is None

    assert tool_start.span_type == SpanType.TOOL
    assert tool_start.operation_name == "web_search"
    assert tool_start.parent_span_id == agent_start.span_id
    assert tool_start.attributes["inputs"]["api_key"] == "[REDACTED]"
    assert tool_end.status == SpanStatus.SUCCEEDED
    assert tool_end.attributes["output"]["result"] == "found for AI Agents"

    assert llm_start.span_type == SpanType.LLM
    assert llm_start.parent_span_id == agent_start.span_id
    assert llm_start.model.provider == "openai"
    assert llm_start.model.name == "gpt-4o"
    assert llm_end.usage.input_tokens == 50
    assert llm_end.usage.output_tokens == 100

    assert agent_end.status == SpanStatus.SUCCEEDED
    assert agent_end.span_id == agent_start.span_id


def test_decorators_exception_handling():
    emitted: list[CanonicalEventV1] = []
    exporter = get_exporter()
    exporter.enqueue = lambda e: emitted.append(e)

    @trace_tool
    def faulty_tool():
        raise RuntimeError("database connection failed")

    with pytest.raises(RuntimeError, match="database connection failed"):
        faulty_tool()

    assert len(emitted) == 2
    assert emitted[0].status == SpanStatus.RUNNING
    assert emitted[1].status == SpanStatus.FAILED
    assert emitted[1].error.error_class == "RuntimeError"
    assert emitted[1].error.message == "database connection failed"
    assert emitted[1].ended_at is not None


# ============================================================================
# 5. LangChain Callback Adapter Tests
# ============================================================================
def test_langchain_callback_adapter():
    emitted: list[CanonicalEventV1] = []
    exporter = get_exporter()
    exporter.enqueue = lambda e: emitted.append(e)

    cb = SentinelLangChainCallback(
        agent_id="lc-agent",
        agent_name="LangChain Test Agent",
        team="qa",
    )

    chain_run_id = uuid.uuid4()
    cb.on_chain_start(
        {"name": "AgentExecutor"},
        {"input": "solve math", "password": "pass"},
        run_id=chain_run_id,
    )

    llm_run_id = uuid.uuid4()
    cb.on_llm_start(
        {"name": "ChatAnthropic", "kwargs": {"model_name": "claude-3-5-sonnet"}},
        ["Calculate 2+2"],
        run_id=llm_run_id,
        parent_run_id=chain_run_id,
        metadata={"ls_provider": "anthropic"},
    )

    llm_result = LLMResult(
        generations=[[Generation(text="4")]],
        llm_output={"token_usage": {"prompt_tokens": 12, "completion_tokens": 4}},
    )
    cb.on_llm_end(llm_result, run_id=llm_run_id, parent_run_id=chain_run_id)

    tool_run_id = uuid.uuid4()
    cb.on_tool_start(
        {"name": "MathTool"},
        "2+2",
        run_id=tool_run_id,
        parent_run_id=chain_run_id,
    )
    cb.on_tool_end("4", run_id=tool_run_id, parent_run_id=chain_run_id)

    cb.on_chain_end({"output": "4"}, run_id=chain_run_id)

    assert len(emitted) == 6
    assert emitted[0].span_type == SpanType.AGENT
    assert emitted[0].attributes["inputs"]["password"] == "[REDACTED]"

    assert emitted[1].span_type == SpanType.LLM
    assert emitted[1].parent_span_id == emitted[0].span_id
    assert emitted[1].model.name == "claude-3-5-sonnet"

    assert emitted[2].usage.input_tokens == 12
    assert emitted[2].usage.output_tokens == 4

    assert emitted[3].span_type == SpanType.TOOL
    assert emitted[3].parent_span_id == emitted[0].span_id

    assert emitted[5].status == SpanStatus.SUCCEEDED
    assert emitted[5].attributes["output"]["output"] == "4"


def test_langchain_callback_error_handling():
    emitted: list[CanonicalEventV1] = []
    exporter = get_exporter()
    exporter.enqueue = lambda e: emitted.append(e)

    cb = SentinelLangChainCallback()
    tool_id = uuid.uuid4()
    cb.on_tool_start({"name": "FailingTool"}, "input", run_id=tool_id)
    cb.on_tool_error(ValueError("Tool failed"), run_id=tool_id)

    assert len(emitted) == 2
    assert emitted[0].status == SpanStatus.RUNNING
    assert emitted[1].status == SpanStatus.FAILED
    assert emitted[1].error.error_class == "ValueError"
    assert emitted[1].error.message == "Tool failed"


def test_load_sdk_env_from_dotenv():
    from sentinel_sdk.config import find_env_file, load_sdk_env

    env_path = find_env_file()
    assert env_path is not None
    assert env_path.name == ".env"

    url, api_key = load_sdk_env()
    assert url.startswith("http")
    assert len(api_key) > 0


def test_load_sdk_env_missing_raises_error(monkeypatch):
    from sentinel_sdk.config import load_sdk_env

    monkeypatch.delenv("SENTINEL_URL", raising=False)
    with pytest.raises(ValueError, match="Missing SENTINEL_URL"):
        load_sdk_env()

    monkeypatch.setenv("SENTINEL_URL", "http://127.0.0.1:8000")
    monkeypatch.delenv("SENTINEL_API_KEY", raising=False)
    with pytest.raises(ValueError, match="Missing SENTINEL_API_KEY"):
        load_sdk_env()

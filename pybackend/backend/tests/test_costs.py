from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient
from sentinel_backend.api.costs import router
from sentinel_backend.db.session import get_db
from sentinel_backend.models.agent import Agent
from sentinel_backend.models.audit import AuditEvent
from sentinel_backend.models.pricing import PricingVersion
from sentinel_backend.models.run import Run
from sentinel_backend.models.span import Span
from sentinel_backend.services.cost_calculator import (
    calculate_run_costs,
    seed_default_pricing,
)
from sentinel_backend.services.lineage_builder import build_run_lineage

# ============================================================================
# Unit Tests: seed_default_pricing
# ============================================================================

@pytest.mark.asyncio
async def test_seed_default_pricing_when_empty():
    mock_db = AsyncMock()
    mock_db.add_all = MagicMock()
    # Mock count query returning 0
    mock_count_res = MagicMock()
    mock_count_res.scalar_one.return_value = 0
    mock_db.execute.return_value = mock_count_res

    await seed_default_pricing(mock_db)

    # Verifies that db.add_all was called with the default pricing models
    assert mock_db.add_all.called
    added_rates = mock_db.add_all.call_args[0][0]
    assert len(added_rates) == 7

    models = {(r.provider, r.model_name): (r.input_rate_per_1m, r.output_rate_per_1m, r.version_tag) for r in added_rates}
    assert ("openai", "gpt-4o") in models
    assert models[("openai", "gpt-4o")] == (Decimal("2.50"), Decimal("10.00"), "2026-11-v1")
    assert ("openai", "gpt-4o-mini") in models
    assert models[("openai", "gpt-4o-mini")] == (Decimal("0.15"), Decimal("0.60"), "2026-11-v1")
    assert ("anthropic", "claude-3-7-sonnet") in models
    assert models[("anthropic", "claude-3-7-sonnet")] == (Decimal("3.00"), Decimal("15.00"), "2026-11-v1")
    assert ("google", "gemini-2.5-pro") in models
    assert models[("google", "gemini-2.5-pro")] == (Decimal("1.25"), Decimal("5.00"), "2026-11-v1")
    assert ("groq", "llama-3.3-70b-versatile") in models
    assert models[("groq", "llama-3.3-70b-versatile")] == (Decimal("0.59"), Decimal("0.79"), "2026-11-v1")
    assert ("google", "gemini-2.5-flash") in models
    assert models[("google", "gemini-2.5-flash")] == (Decimal("0.15"), Decimal("0.60"), "2026-11-v1")
    assert ("huggingface", "deepseek-ai/DeepSeek-R1:fastest") in models
    assert models[("huggingface", "deepseek-ai/DeepSeek-R1:fastest")] == (Decimal("0.55"), Decimal("2.19"), "2026-11-v1")
    assert ("ollama", "llama3.2") not in models

    assert mock_db.commit.called


@pytest.mark.asyncio
async def test_seed_default_pricing_when_not_empty():
    mock_db = AsyncMock()
    mock_count_res = MagicMock()
    mock_count_res.scalar_one.return_value = 4
    mock_db.execute.return_value = mock_count_res

    await seed_default_pricing(mock_db)

    assert not mock_db.add_all.called
    assert not mock_db.commit.called


# ============================================================================
# Unit Tests: calculate_run_costs
# ============================================================================

@pytest.mark.asyncio
async def test_calculate_run_costs_exact_calculation():
    now = datetime.now(UTC)
    run = Run(
        run_id="run_1",
        trace_id="trace_1",
        team="ai-platform",
        status="RUNNING",
        started_at=now,
        last_event_at=now,
        total_tokens=1500,
    )

    pricing_gpt4o = PricingVersion(
        id=1,
        provider="openai",
        model_name="gpt-4o",
        version_tag="2026-11-v1",
        input_rate_per_1m=Decimal("2.50"),
        output_rate_per_1m=Decimal("10.00"),
        effective_from=now,
    )

    span_agent = Span(
        span_id="span_agent",
        trace_id="trace_1",
        run_id="run_1",
        agent_id="agent_1",
        span_type="AGENT",
        operation_name="coordinator",
        status="RUNNING",
        started_at=now,
        direct_cost_usd=Decimal("999.0"),  # Should be cleared to None
    )

    span_llm = Span(
        span_id="span_llm",
        trace_id="trace_1",
        run_id="run_1",
        agent_id="agent_1",
        span_type="LLM",
        operation_name="chat_completion",
        status="SUCCEEDED",
        started_at=now,
        model_provider="openai",
        model_name="gpt-4o",
        input_tokens=1000,
        output_tokens=500,
    )

    mock_db = AsyncMock()
    mock_db.get.return_value = run

    # First execute: spans; Second execute: pricing
    res_spans = MagicMock()
    res_spans.scalars.return_value.all.return_value = [span_agent, span_llm]

    res_pricing = MagicMock()
    res_pricing.scalars.return_value.all.return_value = [pricing_gpt4o]

    mock_db.execute.side_effect = [res_spans, res_pricing]

    await calculate_run_costs(mock_db, "run_1")

    # Non-leaf span direct_cost_usd must be None
    assert span_agent.direct_cost_usd is None

    # Leaf LLM span cost: (1000 * 2.50 + 500 * 10.00) / 1,000,000 = (2500 + 5000) / 1,000,000 = 0.0075
    assert span_llm.direct_cost_usd == Decimal("0.007500")
    assert span_llm.cost_basis == "EXACT"

    # Run rollup
    assert run.total_cost_usd == Decimal("0.007500")
    assert run.cost_status == "EXACT"


@pytest.mark.asyncio
async def test_calculate_run_costs_missing_tokens():
    now = datetime.now(UTC)
    run = Run(
        run_id="run_2",
        trace_id="trace_2",
        team="ai-platform",
        status="RUNNING",
        started_at=now,
        last_event_at=now,
    )

    span_llm = Span(
        span_id="span_llm_missing",
        trace_id="trace_2",
        run_id="run_2",
        agent_id="agent_1",
        span_type="LLM",
        operation_name="chat_completion",
        status="SUCCEEDED",
        started_at=now,
        model_provider="openai",
        model_name="gpt-4o",
        input_tokens=None,  # missing tokens
        output_tokens=100,
    )

    mock_db = AsyncMock()
    mock_db.get.return_value = run

    res_spans = MagicMock()
    res_spans.scalars.return_value.all.return_value = [span_llm]

    res_pricing = MagicMock()
    res_pricing.scalars.return_value.all.return_value = []

    mock_db.execute.side_effect = [res_spans, res_pricing]

    await calculate_run_costs(mock_db, "run_2")

    assert span_llm.direct_cost_usd is None
    assert span_llm.cost_basis == "UNKNOWN"
    assert run.total_cost_usd is None
    assert run.cost_status == "UNKNOWN"


@pytest.mark.asyncio
async def test_calculate_run_costs_unconfigured_model():
    now = datetime.now(UTC)
    run = Run(
        run_id="run_3",
        trace_id="trace_3",
        team="ai-platform",
        status="RUNNING",
        started_at=now,
        last_event_at=now,
    )

    span_llm = Span(
        span_id="span_llm_unknown_model",
        trace_id="trace_3",
        run_id="run_3",
        agent_id="agent_1",
        span_type="LLM",
        operation_name="chat_completion",
        status="SUCCEEDED",
        started_at=now,
        model_provider="custom-ai",
        model_name="unknown-model-xyz",
        input_tokens=500,
        output_tokens=500,
    )

    mock_db = AsyncMock()
    mock_db.get.return_value = run

    res_spans = MagicMock()
    res_spans.scalars.return_value.all.return_value = [span_llm]

    res_pricing = MagicMock()
    res_pricing.scalars.return_value.all.return_value = []

    mock_db.execute.side_effect = [res_spans, res_pricing]

    await calculate_run_costs(mock_db, "run_3")

    assert span_llm.direct_cost_usd is None
    assert span_llm.cost_basis == "UNKNOWN"
    assert run.total_cost_usd is None
    assert run.cost_status == "UNKNOWN"


@pytest.mark.asyncio
async def test_calculate_run_costs_partial_status():
    now = datetime.now(UTC)
    run = Run(
        run_id="run_4",
        trace_id="trace_4",
        team="ai-platform",
        status="RUNNING",
        started_at=now,
        last_event_at=now,
    )

    pricing_claude = PricingVersion(
        id=2,
        provider="anthropic",
        model_name="claude-3-7-sonnet",
        version_tag="2026-11-v1",
        input_rate_per_1m=Decimal("3.00"),
        output_rate_per_1m=Decimal("15.00"),
        effective_from=now,
    )

    # Span 1: known pricing
    span_llm_known = Span(
        span_id="span_1",
        trace_id="trace_4",
        run_id="run_4",
        agent_id="agent_1",
        span_type="LLM",
        operation_name="generate",
        status="SUCCEEDED",
        started_at=now,
        model_provider="anthropic",
        model_name="claude-3-7-sonnet",
        input_tokens=1000,
        output_tokens=1000,
    )
    # Span 2: unconfigured pricing
    span_llm_unknown = Span(
        span_id="span_2",
        trace_id="trace_4",
        run_id="run_4",
        agent_id="agent_1",
        span_type="LLM",
        operation_name="generate",
        status="SUCCEEDED",
        started_at=now,
        model_provider="other",
        model_name="unconfigured-model",
        input_tokens=1000,
        output_tokens=1000,
    )

    mock_db = AsyncMock()
    mock_db.get.return_value = run

    res_spans = MagicMock()
    res_spans.scalars.return_value.all.return_value = [span_llm_known, span_llm_unknown]

    res_pricing = MagicMock()
    res_pricing.scalars.return_value.all.return_value = [pricing_claude]

    mock_db.execute.side_effect = [res_spans, res_pricing]

    await calculate_run_costs(mock_db, "run_4")

    # span_1: (1000 * 3.00 + 1000 * 15.00) / 1,000,000 = 18000 / 1,000,000 = 0.018
    assert span_llm_known.direct_cost_usd == Decimal("0.018000")
    assert span_llm_known.cost_basis == "EXACT"

    # span_2: unknown
    assert span_llm_unknown.direct_cost_usd is None
    assert span_llm_unknown.cost_basis == "UNKNOWN"

    # Run status must be PARTIAL with known sum
    assert run.total_cost_usd == Decimal("0.018000")
    assert run.cost_status == "PARTIAL"


# ============================================================================
# Unit Tests: build_run_lineage rolled_up_cost_usd
# ============================================================================

@pytest.mark.asyncio
async def test_build_run_lineage_rolled_up_cost():
    now = datetime.now(UTC)
    run = Run(
        run_id="run_lineage_cost",
        trace_id="trace_lineage",
        team="ai-platform",
        status="SUCCEEDED",
        started_at=now,
        last_event_at=now,
    )

    # Tree structure:
    # root_agent (AGENT)
    #   ├── tool_1 (TOOL)
    #   │     └── llm_1 (LLM, cost = 0.005)
    #   └── llm_2 (LLM, cost = 0.010)

    root_agent = Span(
        span_id="span_root",
        trace_id="trace_lineage",
        parent_span_id=None,
        run_id="run_lineage_cost",
        agent_id="coordinator",
        span_type="AGENT",
        operation_name="coordinator_agent",
        status="SUCCEEDED",
        started_at=now,
        ended_at=now + timedelta(seconds=2),
        direct_cost_usd=None,
    )
    tool_1 = Span(
        span_id="span_tool",
        trace_id="trace_lineage",
        parent_span_id="span_root",
        run_id="run_lineage_cost",
        agent_id="coordinator",
        span_type="TOOL",
        operation_name="search_db",
        status="SUCCEEDED",
        started_at=now,
        ended_at=now + timedelta(seconds=1),
        direct_cost_usd=None,
    )
    llm_1 = Span(
        span_id="span_llm_1",
        trace_id="trace_lineage",
        parent_span_id="span_tool",
        run_id="run_lineage_cost",
        agent_id="coordinator",
        span_type="LLM",
        operation_name="summarize",
        status="SUCCEEDED",
        started_at=now,
        ended_at=now + timedelta(milliseconds=500),
        direct_cost_usd=Decimal("0.005000"),
    )
    llm_2 = Span(
        span_id="span_llm_2",
        trace_id="trace_lineage",
        parent_span_id="span_root",
        run_id="run_lineage_cost",
        agent_id="coordinator",
        span_type="LLM",
        operation_name="final_answer",
        status="SUCCEEDED",
        started_at=now + timedelta(seconds=1),
        ended_at=now + timedelta(seconds=2),
        direct_cost_usd=Decimal("0.010000"),
    )

    mock_db = AsyncMock()
    mock_db.get.return_value = run

    res_spans = MagicMock()
    res_spans.scalars.return_value.all.return_value = [root_agent, tool_1, llm_1, llm_2]
    mock_db.execute.return_value = res_spans

    graph = await build_run_lineage(mock_db, "run_lineage_cost")

    nodes_by_id = {node.id: node for node in graph.nodes}

    # llm_1 rolled up cost = 0.005
    assert nodes_by_id["span_llm_1"].direct_cost_usd == 0.005
    assert nodes_by_id["span_llm_1"].rolled_up_cost_usd == 0.005

    # llm_2 rolled up cost = 0.010
    assert nodes_by_id["span_llm_2"].direct_cost_usd == 0.01
    assert nodes_by_id["span_llm_2"].rolled_up_cost_usd == 0.01

    # tool_1 rolled up cost = llm_1 (0.005)
    assert nodes_by_id["span_tool"].direct_cost_usd is None
    assert nodes_by_id["span_tool"].rolled_up_cost_usd == 0.005

    # root_agent rolled up cost = llm_1 (0.005) + llm_2 (0.010) = 0.015 without double counting
    assert nodes_by_id["span_root"].direct_cost_usd is None
    assert nodes_by_id["span_root"].rolled_up_cost_usd == 0.015


# ============================================================================
# API Endpoint Tests
# ============================================================================

@pytest.mark.asyncio
async def test_get_pricing_endpoint():
    now = datetime.now(UTC)
    pricing_entry = PricingVersion(
        id=1,
        provider="openai",
        model_name="gpt-4o",
        version_tag="2026-11-v1",
        input_rate_per_1m=Decimal("2.50"),
        output_rate_per_1m=Decimal("10.00"),
        effective_from=now,
    )

    mock_db = AsyncMock()
    res = MagicMock()
    res.scalars.return_value.all.return_value = [pricing_entry]
    mock_db.execute.return_value = res

    async def override_get_db():
        yield mock_db

    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/costs/pricing")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["provider"] == "openai"
        assert data[0]["model_name"] == "gpt-4o"
        assert data[0]["input_rate_per_1m"] == 2.5
        assert data[0]["output_rate_per_1m"] == 10.0


@pytest.mark.asyncio
async def test_post_pricing_requires_approver():
    mock_db = AsyncMock()

    async def override_get_db():
        yield mock_db

    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = override_get_db

    # Calling with viewer role should return 403 Forbidden
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        payload = {
            "provider": "openai",
            "model_name": "gpt-4.5-preview",
            "version_tag": "2026-11-v2",
            "input_rate_per_1m": 75.0,
            "output_rate_per_1m": 150.0,
        }
        resp = await client.post(
            "/api/costs/pricing",
            json=payload,
            headers={"x-actor-role": "viewer", "x-actor-id": "viewer-1"},
        )
        assert resp.status_code == 403
        assert "approver privileges" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_post_pricing_success_and_audit_event():
    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    exec_res = MagicMock()
    exec_res.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = exec_res

    async def fake_refresh(obj):
        if getattr(obj, "id", None) is None:
            obj.id = 42

    mock_db.refresh.side_effect = fake_refresh

    async def override_get_db():
        yield mock_db

    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = override_get_db

    payload = {
        "provider": "openai",
        "model_name": "gpt-4.5-preview",
        "version_tag": "2026-11-v2",
        "input_rate_per_1m": 75.0,
        "output_rate_per_1m": 150.0,
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/costs/pricing",
            json=payload,
            headers={"x-actor-role": "approver", "x-actor-id": "approver-1"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["provider"] == "openai"
        assert data["model_name"] == "gpt-4.5-preview"
        assert data["input_rate_per_1m"] == 75.0

        # Verify AuditEvent was added
        added_objs = [call[0][0] for call in mock_db.add.call_args_list]
        audit_events = [obj for obj in added_objs if isinstance(obj, AuditEvent)]
        assert len(audit_events) == 1
        audit = audit_events[0]
        assert audit.action == "PRICING_UPDATED"
        assert audit.actor_id == "approver-1"
        assert audit.actor_role == "approver"
        assert audit.payload["model_name"] == "gpt-4.5-preview"


@pytest.mark.asyncio
async def test_get_costs_summary():
    now = datetime.now(UTC)
    agent = Agent(
        agent_id="test_agent",
        display_name="Test Agent",
        framework="custom",
        team="infra",
        status="ACTIVE",
        last_seen_at=now,
    )
    run = Run(
        run_id="run_sum_1",
        trace_id="trace_sum_1",
        team="infra",
        status="SUCCEEDED",
        started_at=now,
        last_event_at=now,
        total_tokens=3000,
        total_cost_usd=Decimal("0.015000"),
        cost_status="EXACT",
    )
    span_llm = Span(
        span_id="span_sum_llm",
        trace_id="trace_sum_1",
        run_id="run_sum_1",
        agent_id="test_agent",
        span_type="LLM",
        operation_name="generate",
        status="SUCCEEDED",
        started_at=now,
        model_provider="openai",
        model_name="gpt-4o",
        input_tokens=2000,
        output_tokens=1000,
        direct_cost_usd=Decimal("0.015000"),
        cost_basis="EXACT",
    )

    mock_db = AsyncMock()

    res_runs = MagicMock()
    res_runs.scalars.return_value.all.return_value = [run]

    res_agents = MagicMock()
    res_agents.scalars.return_value.all.return_value = [agent]

    res_spans = MagicMock()
    res_spans.scalars.return_value.all.return_value = [span_llm]

    mock_db.execute.side_effect = [res_runs, res_agents, res_spans]

    async def override_get_db():
        yield mock_db

    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/costs/summary")
        assert resp.status_code == 200
        data = resp.json()

        assert data["total_known_cost_usd"] == 0.015
        assert data["total_tokens"] == 3000
        assert data["unknown_usage_spans_count"] == 0

        # by_agent
        assert len(data["by_agent"]) == 1
        assert data["by_agent"][0]["key"] == "test_agent"
        assert data["by_agent"][0]["total_cost_usd"] == 0.015

        # by_team
        assert len(data["by_team"]) == 1
        assert data["by_team"][0]["key"] == "infra"

        # by_model
        assert len(data["by_model"]) == 1
        assert data["by_model"][0]["key"] == "gpt-4o"

        # by_run
        assert len(data["by_run"]) == 1
        assert data["by_run"][0]["key"] == "run_sum_1"
        assert data["by_run"][0]["total_cost_usd"] == 0.015


@pytest.mark.asyncio
async def test_ingest_telemetry_batch_invokes_calculate_run_costs():
    from unittest.mock import patch

    from sentinel_backend.services.ingestion import ingest_telemetry_batch
    from sentinel_sdk.schema import CanonicalEventV1, SpanStatus, SpanType

    mock_db = AsyncMock()
    mock_token_res = MagicMock()
    mock_token_res.scalar_one.return_value = 1500

    mock_run_res = MagicMock()
    mock_run = MagicMock()
    mock_run.run_id = "run_ingest_1"
    mock_run.trace_id = "trace_1"
    mock_run.root_agent_id = "agent_1"
    mock_run.team = "default"
    mock_run.status = "RUNNING"
    mock_run.started_at = datetime.now(UTC)
    mock_run.ended_at = None
    mock_run.last_event_at = datetime.now(UTC)
    mock_run.total_tokens = 1500
    mock_run.total_cost_usd = 0.0075
    mock_run.cost_status = "EXACT"
    mock_run_res.scalar_one_or_none.return_value = mock_run

    mock_db.execute.side_effect = [
        None,  # agent insert
        None,  # run insert
        None,  # span insert
        mock_token_res,  # total_tokens sum query
        None,  # update run
        mock_run_res,  # select run for redis
    ]

    called_order = []

    async def fake_calculate_run_costs(db, run_id):
        called_order.append(("calculate_run_costs", run_id))

    async def fake_evaluate_anomalies(db, run_id):
        called_order.append(("evaluate_run_anomalies", run_id))

    async def fake_publish_event(*args, **kwargs):
        pass

    with patch("sentinel_backend.services.ingestion.calculate_run_costs", side_effect=fake_calculate_run_costs), \
         patch("sentinel_backend.services.ingestion.evaluate_run_anomalies", side_effect=fake_evaluate_anomalies), \
         patch("sentinel_backend.services.ingestion.publish_event", side_effect=fake_publish_event):

        event = CanonicalEventV1(
            event_id="evt_1",
            trace_id="trace_1",
            span_id="span_1",
            run_id="run_ingest_1",
            agent_id="agent_1",
            span_type=SpanType.LLM,
            operation_name="chat",
            status=SpanStatus.SUCCEEDED,
            started_at=datetime.now(UTC),
        )

        res = await ingest_telemetry_batch(mock_db, [event])
        assert res["accepted"] == 1
        assert "run_ingest_1" in res["run_ids"]

        # Assert calculate_run_costs was called BEFORE evaluate_run_anomalies
        assert called_order == [
            ("calculate_run_costs", "run_ingest_1"),
            ("evaluate_run_anomalies", "run_ingest_1"),
        ]
        assert mock_db.commit.called

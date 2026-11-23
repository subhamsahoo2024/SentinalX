from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError
from sentinel_backend.models.policy import Policy
from sentinel_backend.schemas.policies import (
    PolicyCreate,
    PolicyDTO,
    PolicyUpdate,
)
from sentinel_backend.services.policy_service import (
    resolve_effective_policy,
    seed_default_policy,
)


# ==============================================================================
# Model Tests
# ==============================================================================
def test_policy_model_instantiation():
    now = datetime.now(UTC)
    p = Policy(
        policy_id="pol_test_1",
        name="Test Policy",
        team="security",
        agent_id="audit_agent",
        max_tokens=8000,
        max_cost_usd=Decimal("1.2500"),
        loop_threshold=5,
        loop_window_sec=45,
        auto_block_on_budget=True,
        protected_tools=["delete_database", "restart_production_cluster"],
        enabled=True,
        updated_at=now,
    )
    assert p.policy_id == "pol_test_1"
    assert p.name == "Test Policy"
    assert p.team == "security"
    assert p.agent_id == "audit_agent"
    assert p.max_tokens == 8000
    assert p.max_cost_usd == Decimal("1.2500")
    assert p.loop_threshold == 5
    assert p.loop_window_sec == 45
    assert p.auto_block_on_budget is True
    assert p.protected_tools == ["delete_database", "restart_production_cluster"]
    assert p.enabled is True
    assert p.updated_at == now


# ==============================================================================
# Schema Tests
# ==============================================================================
def test_policy_create_defaults():
    pc = PolicyCreate(name="Default Schema Policy")
    assert pc.name == "Default Schema Policy"
    assert pc.team is None
    assert pc.agent_id is None
    assert pc.max_tokens == 5000
    assert pc.max_cost_usd == 0.50
    assert pc.loop_threshold == 3
    assert pc.loop_window_sec == 30
    assert pc.auto_block_on_budget is False
    assert pc.protected_tools == []
    assert pc.enabled is True


def test_policy_create_forbids_extra_fields():
    with pytest.raises(ValidationError):
        PolicyCreate(name="Bad Policy", extra_unknown_field="invalid")


def test_policy_update_all_optional():
    pu = PolicyUpdate()
    assert pu.name is None
    assert pu.team is None
    assert pu.agent_id is None
    assert pu.max_tokens is None
    assert pu.max_cost_usd is None
    assert pu.loop_threshold is None
    assert pu.loop_window_sec is None
    assert pu.auto_block_on_budget is None
    assert pu.protected_tools is None
    assert pu.enabled is None

    pu2 = PolicyUpdate(max_tokens=10000, auto_block_on_budget=True)
    assert pu2.max_tokens == 10000
    assert pu2.auto_block_on_budget is True


def test_policy_dto_from_attributes():
    now = datetime.now(UTC)
    model = Policy(
        policy_id="pol_dto_test",
        name="DTO Policy",
        team="platform",
        agent_id=None,
        max_tokens=6000,
        max_cost_usd=Decimal("0.7500"),
        loop_threshold=4,
        loop_window_sec=20,
        auto_block_on_budget=True,
        protected_tools=["shutdown_vm"],
        enabled=True,
        updated_at=now,
    )
    dto = PolicyDTO.model_validate(model)
    assert dto.policy_id == "pol_dto_test"
    assert dto.name == "DTO Policy"
    assert dto.team == "platform"
    assert dto.agent_id is None
    assert dto.max_tokens == 6000
    assert dto.max_cost_usd == 0.75
    assert dto.loop_threshold == 4
    assert dto.loop_window_sec == 20
    assert dto.auto_block_on_budget is True
    assert dto.protected_tools == ["shutdown_vm"]
    assert dto.enabled is True
    assert dto.updated_at == now


# ==============================================================================
# Service Tests: seed_default_policy
# ==============================================================================
@pytest.mark.asyncio
async def test_seed_default_policy_when_empty():
    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    mock_count_res = MagicMock()
    mock_count_res.scalar_one.return_value = 0
    mock_db.execute.return_value = mock_count_res

    await seed_default_policy(mock_db)

    assert mock_db.add.called
    added_policy = mock_db.add.call_args[0][0]
    assert added_policy.policy_id == "pol_default"
    assert added_policy.name == "Global Default Governance Policy"
    assert added_policy.team is None
    assert added_policy.agent_id is None
    assert added_policy.max_tokens == 5000
    assert added_policy.max_cost_usd == Decimal("0.5000")
    assert added_policy.loop_threshold == 3
    assert added_policy.loop_window_sec == 30
    assert added_policy.auto_block_on_budget is False
    assert added_policy.protected_tools == ["restart_production_cluster"]
    assert added_policy.enabled is True
    assert mock_db.commit.called


@pytest.mark.asyncio
async def test_seed_default_policy_when_not_empty():
    mock_db = AsyncMock()
    mock_count_res = MagicMock()
    mock_count_res.scalar_one.return_value = 1
    mock_db.execute.return_value = mock_count_res

    await seed_default_policy(mock_db)

    assert not mock_db.add.called
    assert not mock_db.commit.called


# ==============================================================================
# Service Tests: resolve_effective_policy
# ==============================================================================
@pytest.mark.asyncio
async def test_resolve_effective_policy_priority_agent():
    mock_db = AsyncMock()
    now = datetime.now(UTC)

    pol_global = Policy(
        policy_id="pol_default",
        name="Global",
        team=None,
        agent_id=None,
        max_tokens=5000,
        max_cost_usd=Decimal("0.5000"),
        loop_threshold=3,
        loop_window_sec=30,
        auto_block_on_budget=False,
        protected_tools=[],
        enabled=True,
        updated_at=now,
    )
    pol_team = Policy(
        policy_id="pol_secops",
        name="SecOps Team",
        team="secops",
        agent_id=None,
        max_tokens=8000,
        max_cost_usd=Decimal("1.0000"),
        loop_threshold=4,
        loop_window_sec=30,
        auto_block_on_budget=False,
        protected_tools=[],
        enabled=True,
        updated_at=now,
    )
    pol_agent = Policy(
        policy_id="pol_bot",
        name="Bot Specific",
        team=None,
        agent_id="bot_1",
        max_tokens=15000,
        max_cost_usd=Decimal("2.5000"),
        loop_threshold=6,
        loop_window_sec=60,
        auto_block_on_budget=True,
        protected_tools=["restart_production_cluster"],
        enabled=True,
        updated_at=now,
    )

    mock_res = MagicMock()
    mock_res.scalars.return_value.all.return_value = [pol_global, pol_team, pol_agent]
    mock_db.execute.return_value = mock_res

    resolved = await resolve_effective_policy(mock_db, team="secops", agent_id="bot_1")
    assert resolved.policy_id == "pol_bot"
    assert resolved.max_tokens == 15000


@pytest.mark.asyncio
async def test_resolve_effective_policy_priority_team():
    mock_db = AsyncMock()
    now = datetime.now(UTC)

    pol_global = Policy(
        policy_id="pol_default",
        name="Global",
        team=None,
        agent_id=None,
        max_tokens=5000,
        max_cost_usd=Decimal("0.5000"),
        loop_threshold=3,
        loop_window_sec=30,
        auto_block_on_budget=False,
        protected_tools=[],
        enabled=True,
        updated_at=now,
    )
    pol_team = Policy(
        policy_id="pol_secops",
        name="SecOps Team",
        team="secops",
        agent_id=None,
        max_tokens=8000,
        max_cost_usd=Decimal("1.0000"),
        loop_threshold=4,
        loop_window_sec=30,
        auto_block_on_budget=False,
        protected_tools=[],
        enabled=True,
        updated_at=now,
    )

    mock_res = MagicMock()
    mock_res.scalars.return_value.all.return_value = [pol_global, pol_team]
    mock_db.execute.return_value = mock_res

    # Query with agent_id="unknown_agent" (no agent match) -> matches team
    resolved = await resolve_effective_policy(mock_db, team="secops", agent_id="unknown_agent")
    assert resolved.policy_id == "pol_secops"
    assert resolved.max_tokens == 8000

    # Query with agent_id=None -> matches team
    resolved_none_agent = await resolve_effective_policy(mock_db, team="secops", agent_id=None)
    assert resolved_none_agent.policy_id == "pol_secops"


@pytest.mark.asyncio
async def test_resolve_effective_policy_priority_global():
    mock_db = AsyncMock()
    now = datetime.now(UTC)

    pol_global = Policy(
        policy_id="pol_default",
        name="Global",
        team=None,
        agent_id=None,
        max_tokens=5000,
        max_cost_usd=Decimal("0.5000"),
        loop_threshold=3,
        loop_window_sec=30,
        auto_block_on_budget=False,
        protected_tools=["restart_production_cluster"],
        enabled=True,
        updated_at=now,
    )

    mock_res = MagicMock()
    mock_res.scalars.return_value.all.return_value = [pol_global]
    mock_db.execute.return_value = mock_res

    # Team doesn't match, agent doesn't match -> matches global
    resolved = await resolve_effective_policy(mock_db, team="finance", agent_id="finance_bot")
    assert resolved.policy_id == "pol_default"
    assert resolved.max_tokens == 5000


@pytest.mark.asyncio
async def test_resolve_effective_policy_fallback_synthetic():
    mock_db = AsyncMock()
    mock_res = MagicMock()
    mock_res.scalars.return_value.all.return_value = []
    mock_db.execute.return_value = mock_res

    resolved = await resolve_effective_policy(mock_db, team="finance", agent_id="bot_x")
    assert resolved.policy_id == "pol_default"
    assert resolved.name == "Global Default Governance Policy"
    assert resolved.team is None
    assert resolved.agent_id is None
    assert resolved.max_tokens == 5000
    assert resolved.max_cost_usd == Decimal("0.5000")
    assert resolved.protected_tools == ["restart_production_cluster"]
    assert resolved.enabled is True

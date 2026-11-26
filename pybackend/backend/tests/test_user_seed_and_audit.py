from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sentinel_backend.config import settings
from sentinel_backend.models import Team, UserAccount
from sentinel_backend.models.audit import AuditEvent
from sentinel_backend.schemas.governance import AuditEventDTO
from sentinel_backend.services.user_seed import (
    DEFAULT_TEAMS,
    DEFAULT_USERS,
    password_hash_helper,
    seed_default_users,
)


def test_auth_settings_defaults():
    assert hasattr(settings, "JWT_SECRET")
    assert isinstance(settings.JWT_SECRET, str)
    assert len(settings.JWT_SECRET) >= 32
    assert hasattr(settings, "JWT_EXPIRE_MINUTES")
    assert settings.JWT_EXPIRE_MINUTES == 480
    assert hasattr(settings, "ALLOW_DEV_HEADERS")
    assert settings.ALLOW_DEV_HEADERS is True
    assert settings.ENABLE_DEMO_SANDBOX is True
    assert settings.INITIAL_ADMIN_EMAIL is None
    assert settings.INITIAL_ADMIN_PASSWORD is None
    assert settings.effective_allow_dev_headers is True

    with patch.object(settings, "ENABLE_DEMO_SANDBOX", False):
        assert settings.effective_allow_dev_headers is False

    with patch.object(settings, "ALLOW_DEV_HEADERS", False):
        assert settings.effective_allow_dev_headers is False


def test_team_model():
    now = datetime.now(UTC)
    team = Team(
        team_id="fraud-detection",
        display_name="Fraud Detection",
        description="Fraud risk scoring agents",
        created_at=now,
    )
    assert team.team_id == "fraud-detection"
    assert team.display_name == "Fraud Detection"
    assert team.description == "Fraud risk scoring agents"
    assert team.created_at == now

    minimal_team = Team(team_id="it-ops", display_name="IT Operations")
    assert minimal_team.description is None


def test_user_account_model():
    now = datetime.now(UTC)
    user = UserAccount(
        user_id="usr_approver",
        email="approver@sentinel.local",
        display_name="Arjun Mehta (Approver)",
        password_hash="argon2_mock_hash",
        role="approver",
        created_at=now,
    )
    assert user.user_id == "usr_approver"
    assert user.email == "approver@sentinel.local"
    assert user.display_name == "Arjun Mehta (Approver)"
    assert user.password_hash == "argon2_mock_hash"
    assert user.role == "approver"
    assert user.allowed_teams == ["*"]
    assert user.is_active is True
    assert user.is_demo_account is False
    assert user.created_at == now


def test_audit_event_hash_chain_defaults():
    now = datetime.now(UTC)
    audit = AuditEvent(
        audit_id="audit_hashchain123",
        actor_id="usr_admin",
        actor_role="admin",
        action="POLICY_UPDATE",
        target_type="policy",
        target_id="pol_default",
        payload={"change": "updated"},
        created_at=now,
    )
    assert audit.prev_hash == "GENESIS"
    assert audit.entry_hash == ""

    # Check with explicit hashes
    audit_explicit = AuditEvent(
        audit_id="audit_hashchain456",
        actor_id="usr_admin",
        actor_role="admin",
        action="POLICY_UPDATE",
        target_type="policy",
        target_id="pol_default",
        payload={"change": "updated"},
        prev_hash="a" * 64,
        entry_hash="b" * 64,
        created_at=now,
    )
    assert audit_explicit.prev_hash == "a" * 64
    assert audit_explicit.entry_hash == "b" * 64


def test_audit_event_dto_with_hash_chain():
    now = datetime.now(UTC)
    audit = AuditEvent(
        audit_id="audit_hashchain789",
        actor_id="usr_admin",
        actor_role="admin",
        action="APPROVAL_APPROVED",
        target_type="approval",
        target_id="apr_12345",
        payload={"comment": "LGTM"},
        prev_hash="c" * 64,
        entry_hash="d" * 64,
        created_at=now,
    )
    dto = AuditEventDTO.model_validate(audit)
    assert dto.audit_id == "audit_hashchain789"
    assert dto.prev_hash == "c" * 64
    assert dto.entry_hash == "d" * 64

    # Default values when unpopulated
    dto_default = AuditEventDTO(
        audit_id="audit_default",
        actor_id="usr_1",
        actor_role="operator",
        action="TRIGGER",
        target_type="run",
        target_id="run_1",
        created_at=now,
    )
    assert dto_default.prev_hash == "GENESIS"
    assert dto_default.entry_hash == ""


@pytest.mark.asyncio
async def test_seed_default_users_when_empty():
    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_result

    added_objects: list[object] = []
    mock_db.add.side_effect = lambda obj: added_objects.append(obj)

    with (
        patch.object(settings, "ENABLE_DEMO_SANDBOX", True),
        patch.object(settings, "INITIAL_ADMIN_EMAIL", None),
        patch.object(settings, "INITIAL_ADMIN_PASSWORD", None),
    ):
        await seed_default_users(mock_db)

    added_teams = [obj for obj in added_objects if isinstance(obj, Team)]
    added_users = [obj for obj in added_objects if isinstance(obj, UserAccount)]

    assert len(added_teams) == 4
    assert len(DEFAULT_TEAMS) == 4
    assert {t.team_id: t.display_name for t in added_teams} == {
        "it-ops": "IT Operations",
        "customer-support": "Customer Support",
        "fraud-detection": "Fraud Detection",
        "demo-sandbox": "Demo Sandbox",
    }

    assert len(added_users) == 4
    assert len(DEFAULT_USERS) == 4
    emails = [u.email for u in added_users]
    roles = [u.role for u in added_users]
    user_ids = [u.user_id for u in added_users]

    assert "admin@sentinel.local" in emails
    assert "approver@sentinel.local" in emails
    assert "operator@sentinel.local" in emails
    assert "viewer@sentinel.local" in emails

    assert "admin" in roles
    assert "approver" in roles
    assert "operator" in roles
    assert "viewer" in roles

    assert "usr_admin" in user_ids
    assert "usr_approver" in user_ids
    assert "usr_operator" in user_ids
    assert "usr_viewer" in user_ids

    # Verify password hash, demo flag, and sandbox team scope on all demo accounts
    for user in added_users:
        assert password_hash_helper.verify("sentinel123", user.password_hash)
        assert user.is_demo_account is True
        assert user.allowed_teams == ["demo-sandbox"]
        assert user.is_active is True

    mock_db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_seed_default_users_demo_sandbox_disabled_and_initial_admin():
    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_result

    added_objects: list[object] = []
    mock_db.add.side_effect = lambda obj: added_objects.append(obj)

    with (
        patch.object(settings, "ENABLE_DEMO_SANDBOX", False),
        patch.object(settings, "INITIAL_ADMIN_EMAIL", "Root.Admin@example.com"),
        patch.object(settings, "INITIAL_ADMIN_PASSWORD", "prod-admin-pass-123"),
    ):
        await seed_default_users(mock_db)

    added_teams = [obj for obj in added_objects if isinstance(obj, Team)]
    added_users = [obj for obj in added_objects if isinstance(obj, UserAccount)]

    assert len(added_teams) == 4
    assert len(added_users) == 1

    real_admin = added_users[0]
    assert real_admin.email == "root.admin@example.com"
    assert real_admin.role == "admin"
    assert real_admin.allowed_teams == ["*"]
    assert real_admin.is_demo_account is False
    assert real_admin.is_active is True
    assert password_hash_helper.verify("prod-admin-pass-123", real_admin.password_hash)
    mock_db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_seed_default_users_idempotent_when_already_populated():
    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = MagicMock(spec=UserAccount)
    mock_db.execute.return_value = mock_result

    added_objects: list[object] = []
    mock_db.add.side_effect = lambda obj: added_objects.append(obj)

    with (
        patch.object(settings, "ENABLE_DEMO_SANDBOX", True),
        patch.object(settings, "INITIAL_ADMIN_EMAIL", "admin@example.com"),
        patch.object(settings, "INITIAL_ADMIN_PASSWORD", "secret"),
    ):
        await seed_default_users(mock_db)

    assert len(added_objects) == 0
    mock_db.commit.assert_not_awaited()

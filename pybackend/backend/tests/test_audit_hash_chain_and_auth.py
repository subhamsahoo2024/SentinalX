from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import MagicMock, patch

import jwt
import pytest
from httpx import ASGITransport, AsyncClient
from pwdlib import PasswordHash
from sentinel_backend.api.deps import get_current_actor
from sentinel_backend.config import settings
from sentinel_backend.db.session import get_db
from sentinel_backend.main import app
from sentinel_backend.models.audit import AuditEvent
from sentinel_backend.models.user import UserAccount
from sentinel_backend.services.audit import (
    _compute_entry_hash,
    append_audit_event,
    verify_audit_chain,
)


class InMemoryAuditDB:
    def __init__(self, events: list[AuditEvent] | None = None, users: list[UserAccount] | None = None):
        self.events: list[AuditEvent] = list(events or [])
        self.users: list[UserAccount] = list(users or [])

    async def execute(self, stmt: Any) -> Any:
        stmt_str = str(stmt).lower()
        if "user_accounts" in stmt_str:
            mock_res = MagicMock()
            email = None
            if hasattr(stmt, "_where_criteria") and stmt._where_criteria:
                for crit in stmt._where_criteria:
                    if hasattr(crit, "right") and hasattr(crit.right, "value"):
                        email = str(crit.right.value).lower()
            matched = [u for u in self.users if u.email.lower() == email] if email else self.users
            mock_res.scalar_one_or_none.return_value = matched[0] if matched else None
            return mock_res

        mock_res = MagicMock()
        if "order by audit_events.created_at desc" in stmt_str or "desc" in stmt_str:
            sorted_events = sorted(
                self.events,
                key=lambda x: (x.created_at, x.audit_id),
                reverse=True,
            )
            mock_res.scalar_one_or_none.return_value = sorted_events[0] if sorted_events else None
            mock_res.scalars.return_value.all.return_value = sorted_events
        else:
            sorted_events = sorted(
                self.events,
                key=lambda x: (x.created_at, x.audit_id),
            )
            mock_res.scalars.return_value.all.return_value = sorted_events
            mock_res.scalar_one_or_none.return_value = sorted_events[0] if sorted_events else None
        return mock_res

    def add(self, obj: Any) -> None:
        if isinstance(obj, AuditEvent):
            self.events.append(obj)
        elif isinstance(obj, UserAccount):
            self.users.append(obj)

    async def flush(self) -> None:
        pass

    async def commit(self) -> None:
        pass

    async def refresh(self, obj: Any) -> None:
        pass


# ==============================================================================
# Unit Tests: Hash Computation & Hash-Chain Service
# ==============================================================================
def test_compute_entry_hash_determinism():
    payload = {"run_id": "run_123", "action": "approved"}
    hash1 = _compute_entry_hash(
        prev_hash="GENESIS",
        audit_id="audit_1",
        actor_id="user@sentinel.local",
        actor_role="admin",
        action="APPROVAL_APPROVED",
        target_type="approval",
        target_id="apr_1",
        payload=payload,
    )
    hash2 = _compute_entry_hash(
        prev_hash="GENESIS",
        audit_id="audit_1",
        actor_id="user@sentinel.local",
        actor_role="admin",
        action="APPROVAL_APPROVED",
        target_type="approval",
        target_id="apr_1",
        payload=payload,
    )
    assert hash1 == hash2
    assert len(hash1) == 64

    # Any change modifies the hash
    hash3 = _compute_entry_hash(
        prev_hash="DIFFERENT_HASH",
        audit_id="audit_1",
        actor_id="user@sentinel.local",
        actor_role="admin",
        action="APPROVAL_APPROVED",
        target_type="approval",
        target_id="apr_1",
        payload=payload,
    )
    assert hash1 != hash3


@pytest.mark.asyncio
async def test_append_audit_event_and_chain_verification():
    mock_db = InMemoryAuditDB()

    # 1. First event uses GENESIS
    event1 = await append_audit_event(
        db=mock_db,
        actor_id="usr_admin",
        actor_role="admin",
        action="POLICY_CREATED",
        target_type="policy",
        target_id="pol_1",
        payload={"name": "test policy"},
    )
    assert event1.prev_hash == "GENESIS"
    assert len(event1.entry_hash) == 64

    # 2. Second event uses event1.entry_hash
    event2 = await append_audit_event(
        db=mock_db,
        actor_id="usr_approver",
        actor_role="approver",
        action="APPROVAL_APPROVED",
        target_type="approval",
        target_id="apr_1",
        payload={"comment": "LGTM"},
    )
    assert event2.prev_hash == event1.entry_hash
    assert len(event2.entry_hash) == 64

    # 3. Third event uses event2.entry_hash
    event3 = await append_audit_event(
        db=mock_db,
        actor_id="usr_operator",
        actor_role="operator",
        action="RUN_CANCELLED",
        target_type="run",
        target_id="run_1",
        payload={"status": "CANCELLED"},
    )
    assert event3.prev_hash == event2.entry_hash

    # Verify chain passes
    verify_result = await verify_audit_chain(mock_db)
    assert verify_result["valid"] is True
    assert verify_result["total_events"] == 3
    assert verify_result["latest_hash"] == event3.entry_hash
    assert verify_result["broken_at_audit_id"] is None


@pytest.mark.asyncio
async def test_verify_audit_chain_detects_tampered_prev_hash():
    mock_db = InMemoryAuditDB()

    await append_audit_event(
        db=mock_db,
        actor_id="usr_admin",
        actor_role="admin",
        action="POLICY_CREATED",
        target_type="policy",
        target_id="pol_1",
        payload={"key": "val1"},
    )
    event2 = await append_audit_event(
        db=mock_db,
        actor_id="usr_admin",
        actor_role="admin",
        action="POLICY_UPDATED",
        target_type="policy",
        target_id="pol_1",
        payload={"key": "val2"},
    )

    # Tamper with event2.prev_hash
    event2.prev_hash = "TAMPERED_PREV_HASH"

    verify_result = await verify_audit_chain(mock_db)
    assert verify_result["valid"] is False
    assert verify_result["broken_at_audit_id"] == event2.audit_id


@pytest.mark.asyncio
async def test_verify_audit_chain_detects_tampered_payload():
    mock_db = InMemoryAuditDB()

    event1 = await append_audit_event(
        db=mock_db,
        actor_id="usr_admin",
        actor_role="admin",
        action="POLICY_CREATED",
        target_type="policy",
        target_id="pol_1",
        payload={"key": "val1"},
    )

    # Tamper with payload without updating entry_hash
    event1.payload = {"key": "maliciously_modified"}

    verify_result = await verify_audit_chain(mock_db)
    assert verify_result["valid"] is False
    assert verify_result["broken_at_audit_id"] == event1.audit_id


# ==============================================================================
# Unit & Integration Tests: Auth API & JWT Token Decoding
# ==============================================================================
@pytest.mark.asyncio
async def test_auth_login_success_and_me():
    hasher = PasswordHash.recommended()
    pwd_hash = hasher.hash("secret123")
    demo_user = UserAccount(
        user_id="usr_test_approver",
        email="test_approver@sentinel.local",
        display_name="Test Approver",
        password_hash=pwd_hash,
        role="approver",
        created_at=datetime.now(UTC),
    )
    mock_db = InMemoryAuditDB(users=[demo_user])
    app.dependency_overrides[get_db] = lambda: mock_db

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # 1. Successful login
            login_resp = await client.post(
                "/api/auth/login",
                json={"email": "test_approver@sentinel.local", "password": "secret123"},
            )
            assert login_resp.status_code == 200
            data = login_resp.json()
            assert "access_token" in data
            assert data["token_type"] == "bearer"
            assert data["user"]["email"] == "test_approver@sentinel.local"
            assert data["user"]["role"] == "approver"
            token = data["access_token"]

            # 2. Call /api/auth/me with Bearer token
            me_resp = await client.get(
                "/api/auth/me",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert me_resp.status_code == 200
            me_data = me_resp.json()
            assert me_data["actor_id"] == "test_approver@sentinel.local"
            assert me_data["actor_role"] == "approver"
            assert me_data["display_name"] == "Test Approver"

            # 3. Call /api/audit-events/verify
            verify_resp = await client.get("/api/audit-events/verify")
            assert verify_resp.status_code == 200
            verify_data = verify_resp.json()
            assert verify_data["valid"] is True
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_auth_login_invalid_credentials():
    hasher = PasswordHash.recommended()
    demo_user = UserAccount(
        user_id="usr_test_user",
        email="user@sentinel.local",
        display_name="User",
        password_hash=hasher.hash("correct_password"),
        role="operator",
        created_at=datetime.now(UTC),
    )
    mock_db = InMemoryAuditDB(users=[demo_user])
    app.dependency_overrides[get_db] = lambda: mock_db

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Wrong password
            resp1 = await client.post(
                "/api/auth/login",
                json={"email": "user@sentinel.local", "password": "wrong_password"},
            )
            assert resp1.status_code == 401

            # Non-existent email
            resp2 = await client.post(
                "/api/auth/login",
                json={"email": "nobody@sentinel.local", "password": "any"},
            )
            assert resp2.status_code == 401
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_jwt_auth_expired_token():
    # Construct an expired token
    expired_exp = datetime.now(UTC) - timedelta(minutes=10)
    expired_token = jwt.encode(
        {"sub": "usr_exp", "email": "exp@sentinel.local", "name": "Exp", "role": "viewer", "exp": expired_exp},
        settings.JWT_SECRET,
        algorithm="HS256",
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {expired_token}"},
        )
        assert resp.status_code == 401


@pytest.mark.asyncio
async def test_jwt_auth_invalid_signature():
    token = jwt.encode(
        {"sub": "usr_bad", "email": "bad@sentinel.local", "name": "Bad", "role": "viewer"},
        "wrong-secret-key-123456789012345",
        algorithm="HS256",
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 401


@pytest.mark.asyncio
async def test_get_current_actor_dev_headers_fallback():
    # When ALLOW_DEV_HEADERS is True and no Bearer token is provided
    actor = await get_current_actor(
        authorization=None,
        x_actor_id="dev-operator",
        x_actor_role="operator",
    )
    assert actor.actor_id == "dev-operator"
    assert actor.actor_role == "operator"


@pytest.mark.asyncio
async def test_get_current_actor_disallow_dev_headers():
    # When ALLOW_DEV_HEADERS is False and no Bearer token is provided -> 401
    with patch.object(settings, "ALLOW_DEV_HEADERS", False):
        with pytest.raises(Exception) as exc_info:
            await get_current_actor(
                authorization=None,
                x_actor_id="dev-operator",
                x_actor_role="operator",
            )
        assert "401" in str(exc_info.value)

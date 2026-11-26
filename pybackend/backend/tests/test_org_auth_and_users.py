from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import MagicMock, patch

import jwt
import pytest
from httpx import ASGITransport, AsyncClient
from pwdlib import PasswordHash
from sentinel_backend.api.deps import ActorContext, get_current_actor, require_admin
from sentinel_backend.config import settings
from sentinel_backend.db.session import get_db
from sentinel_backend.main import app
from sentinel_backend.models.audit import AuditEvent
from sentinel_backend.models.team import Team
from sentinel_backend.models.user import UserAccount


class InMemoryOrgDB:
    """Lightweight async in-memory DB double for auth, system, and user/team endpoints."""

    def __init__(
        self,
        users: list[UserAccount] | None = None,
        teams: list[Team] | None = None,
        events: list[AuditEvent] | None = None,
    ) -> None:
        self.users: list[UserAccount] = list(users or [])
        self.teams: list[Team] = list(teams or [])
        self.events: list[AuditEvent] = list(events or [])

    async def get(self, model: type[Any], key: str) -> Any:
        if model is Team:
            return next((t for t in self.teams if t.team_id == key), None)
        if model is UserAccount:
            return next((u for u in self.users if u.user_id == key), None)
        return None

    async def execute(self, stmt: Any) -> Any:
        stmt_str = str(stmt).lower()
        res = MagicMock()

        if "from audit_events" in stmt_str:
            sorted_events = sorted(
                self.events,
                key=lambda x: (x.created_at, x.audit_id),
                reverse="desc" in stmt_str,
            )
            res.scalar_one_or_none.return_value = (
                sorted_events[0] if sorted_events else None
            )
            res.scalars.return_value.all.return_value = sorted_events
            return res

        if "from teams" in stmt_str:
            sorted_teams = sorted(self.teams, key=lambda t: t.display_name)
            res.scalars.return_value.all.return_value = sorted_teams
            res.scalar_one_or_none.return_value = (
                sorted_teams[0] if sorted_teams else None
            )
            return res

        if "count(" in stmt_str and "from user_accounts" in stmt_str:
            non_demo_count = sum(1 for u in self.users if not u.is_demo_account)
            res.scalar_one.return_value = non_demo_count
            return res

        if "from user_accounts" in stmt_str:
            matched = list(self.users)
            if hasattr(stmt, "_where_criteria") and stmt._where_criteria:
                for crit in stmt._where_criteria:
                    col_name = getattr(getattr(crit, "left", None), "name", None)
                    right = getattr(crit, "right", None)
                    val = getattr(right, "value", None)
                    crit_str = str(crit).lower()
                    if col_name == "email" and val is not None:
                        matched = [u for u in matched if u.email == str(val)]
                    elif col_name == "is_demo_account":
                        if "is false" in crit_str or val is False:
                            matched = [u for u in matched if not u.is_demo_account]
                        elif "is true" in crit_str or val is True:
                            matched = [u for u in matched if u.is_demo_account]
            matched.sort(key=lambda u: (u.created_at, u.email))
            res.scalar_one_or_none.return_value = matched[0] if matched else None
            res.scalars.return_value.all.return_value = matched
            return res

        return res

    def add(self, obj: Any) -> None:
        if isinstance(obj, UserAccount):
            self.users.append(obj)
        elif isinstance(obj, Team):
            self.teams.append(obj)
        elif isinstance(obj, AuditEvent):
            self.events.append(obj)

    async def flush(self) -> None:
        pass

    async def commit(self) -> None:
        pass

    async def refresh(self, obj: Any) -> None:
        pass


def _make_jwt(
    *,
    role: str = "admin",
    email: str = "admin@acme.com",
    allowed_teams: list[str] | None = None,
    is_demo: bool = False,
) -> str:
    return jwt.encode(
        {
            "sub": f"usr_{role}",
            "email": email,
            "name": f"Test {role}",
            "role": role,
            "allowed_teams": allowed_teams if allowed_teams is not None else ["*"],
            "is_demo": is_demo,
            "exp": datetime.now(UTC) + timedelta(minutes=30),
        },
        settings.JWT_SECRET,
        algorithm="HS256",
    )


@pytest.mark.asyncio
async def test_deps_jwt_extracts_allowed_teams_and_is_demo():
    token = _make_jwt(
        role="operator",
        email="ops@acme.com",
        allowed_teams=["it-ops", "fraud-detection"],
        is_demo=False,
    )
    actor = await get_current_actor(authorization=f"Bearer {token}")
    assert actor.actor_id == "ops@acme.com"
    assert actor.actor_role == "operator"
    assert actor.allowed_teams == ["it-ops", "fraud-detection"]
    assert actor.is_demo is False


@pytest.mark.asyncio
async def test_require_admin_enforces_admin_role():
    admin_actor = ActorContext(actor_id="a@acme.com", actor_role="admin")
    assert await require_admin(admin_actor) == admin_actor

    approver_actor = ActorContext(actor_id="b@acme.com", actor_role="approver")
    with pytest.raises(Exception) as exc_info:
        await require_admin(approver_actor)
    assert "403" in str(exc_info.value)


@pytest.mark.asyncio
async def test_system_config_needs_bootstrap_true_then_false():
    db = InMemoryOrgDB(
        users=[
            UserAccount(
                user_id="usr_demo",
                email="approver@sentinel.local",
                display_name="Demo Approver",
                password_hash="h",
                role="approver",
                allowed_teams=["demo-sandbox"],
                is_demo_account=True,
                created_at=datetime.now(UTC),
            )
        ]
    )
    app.dependency_overrides[get_db] = lambda: db
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/system/config")
            assert resp.status_code == 200
            assert resp.json() == {
                "demo_sandbox_enabled": settings.ENABLE_DEMO_SANDBOX,
                "needs_bootstrap": True,
            }

            db.users.append(
                UserAccount(
                    user_id="usr_real_admin",
                    email="boss@acme.com",
                    display_name="Boss",
                    password_hash="h",
                    role="admin",
                    is_demo_account=False,
                    created_at=datetime.now(UTC),
                )
            )
            resp2 = await client.get("/api/system/config")
            assert resp2.status_code == 200
            assert resp2.json()["needs_bootstrap"] is False
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_bootstrap_admin_creates_first_admin_and_blocks_second():
    db = InMemoryOrgDB()
    app.dependency_overrides[get_db] = lambda: db
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/auth/bootstrap-admin",
                json={
                    "email": "Founder@Acme.io",
                    "password": "initial-password-123",
                    "display_name": "Founder Admin",
                },
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["token_type"] == "bearer"
            assert data["user"]["email"] == "founder@acme.io"
            assert data["user"]["role"] == "admin"
            assert data["user"]["allowed_teams"] == ["*"]
            assert data["user"]["is_demo"] is False

            claims = jwt.decode(
                data["access_token"], settings.JWT_SECRET, algorithms=["HS256"]
            )
            assert claims["role"] == "admin"
            assert claims["allowed_teams"] == ["*"]
            assert claims["is_demo"] is False

            assert any(e.action == "ADMIN_BOOTSTRAPPED" for e in db.events)

            # Second bootstrap must fail with 403
            resp2 = await client.post(
                "/api/auth/bootstrap-admin",
                json={
                    "email": "attacker@acme.io",
                    "password": "password",
                },
            )
            assert resp2.status_code == 403
            assert "already initialized" in resp2.json()["detail"].lower()
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_login_deactivated_user_returns_403():
    hasher = PasswordHash.recommended()
    inactive_user = UserAccount(
        user_id="usr_inactive",
        email="former@acme.com",
        display_name="Former Employee",
        password_hash=hasher.hash("valid-pass"),
        role="operator",
        allowed_teams=["it-ops"],
        is_active=False,
        is_demo_account=False,
        created_at=datetime.now(UTC),
    )
    db = InMemoryOrgDB(users=[inactive_user])
    app.dependency_overrides[get_db] = lambda: db
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/auth/login",
                json={"email": "former@acme.com", "password": "valid-pass"},
            )
            assert resp.status_code == 403
            assert "deactivated" in resp.json()["detail"].lower()
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_demo_login_success_and_disabled():
    demo_approver = UserAccount(
        user_id="usr_approver",
        email="approver@sentinel.local",
        display_name="Arjun Mehta (Approver)",
        password_hash="unused",
        role="approver",
        allowed_teams=["demo-sandbox"],
        is_active=True,
        is_demo_account=True,
        created_at=datetime.now(UTC),
    )
    db = InMemoryOrgDB(users=[demo_approver])
    app.dependency_overrides[get_db] = lambda: db
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            with patch.object(settings, "ENABLE_DEMO_SANDBOX", True):
                resp = await client.post("/api/auth/demo-login")
                assert resp.status_code == 200
                data = resp.json()
                assert data["user"]["email"] == "approver@sentinel.local"
                assert data["user"]["is_demo"] is True
                assert data["user"]["allowed_teams"] == ["demo-sandbox"]
                claims = jwt.decode(
                    data["access_token"], settings.JWT_SECRET, algorithms=["HS256"]
                )
                assert claims["is_demo"] is True

            with patch.object(settings, "ENABLE_DEMO_SANDBOX", False):
                resp_disabled = await client.post("/api/auth/demo-login")
                assert resp_disabled.status_code == 403
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_admin_teams_and_users_crud_with_audit_logs():
    now = datetime.now(UTC)
    db = InMemoryOrgDB(
        teams=[
            Team(team_id="it-ops", display_name="IT Operations", created_at=now),
            Team(
                team_id="customer-support",
                display_name="Customer Support",
                created_at=now,
            ),
        ],
        users=[
            UserAccount(
                user_id="usr_demo",
                email="viewer@sentinel.local",
                display_name="Demo Viewer",
                password_hash="h",
                role="viewer",
                allowed_teams=["demo-sandbox"],
                is_demo_account=True,
                created_at=now,
            )
        ],
    )
    app.dependency_overrides[get_db] = lambda: db

    admin_token = _make_jwt(role="admin", email="admin@acme.com")
    operator_token = _make_jwt(role="operator", email="ops@acme.com")

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            # GET /api/teams allowed for any authenticated user, sorted by display_name
            teams_resp = await client.get(
                "/api/teams",
                headers={"Authorization": f"Bearer {operator_token}"},
            )
            assert teams_resp.status_code == 200
            assert [t["team_id"] for t in teams_resp.json()] == [
                "customer-support",
                "it-ops",
            ]

            # POST /api/teams forbidden for non-admin
            forbidden_team = await client.post(
                "/api/teams",
                headers={"Authorization": f"Bearer {operator_token}"},
                json={"team_id": "payments", "display_name": "Payments"},
            )
            assert forbidden_team.status_code == 403

            # POST /api/teams succeeds for admin
            create_team = await client.post(
                "/api/teams",
                headers={"Authorization": f"Bearer {admin_token}"},
                json={
                    "team_id": "payments",
                    "display_name": "Payments",
                    "description": "Payment processing agents",
                },
            )
            assert create_team.status_code == 201
            assert create_team.json()["team_id"] == "payments"

            # POST /api/users provisions non-demo user
            create_user = await client.post(
                "/api/users",
                headers={"Authorization": f"Bearer {admin_token}"},
                json={
                    "email": "Alice@Acme.com",
                    "display_name": "Alice Smith",
                    "password": "alice-password-123",
                    "role": "approver",
                    "allowed_teams": ["payments", "it-ops"],
                },
            )
            assert create_user.status_code == 201
            alice = create_user.json()
            assert alice["email"] == "alice@acme.com"
            assert alice["role"] == "approver"
            assert alice["allowed_teams"] == ["payments", "it-ops"]
            assert alice["is_active"] is True

            # GET /api/users lists only non-demo accounts
            list_users = await client.get(
                "/api/users",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
            assert list_users.status_code == 200
            assert len(list_users.json()) == 1
            assert list_users.json()[0]["email"] == "alice@acme.com"

            # PATCH /api/users/{user_id} updates role, allowed_teams, is_active
            patch_user = await client.patch(
                f"/api/users/{alice['user_id']}",
                headers={"Authorization": f"Bearer {admin_token}"},
                json={
                    "role": "operator",
                    "allowed_teams": ["payments"],
                    "is_active": False,
                },
            )
            assert patch_user.status_code == 200
            updated = patch_user.json()
            assert updated["role"] == "operator"
            assert updated["allowed_teams"] == ["payments"]
            assert updated["is_active"] is False

            actions = [e.action for e in db.events]
            assert "TEAM_CREATED" in actions
            assert "USER_PROVISIONED" in actions
            assert "USER_UPDATED" in actions
    finally:
        app.dependency_overrides.clear()


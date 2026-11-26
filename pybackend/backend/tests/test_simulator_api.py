import asyncio
import sys
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import jwt
import pytest
from httpx import ASGITransport, AsyncClient
from sentinel_backend.config import settings
from sentinel_backend.main import app


@pytest.mark.asyncio
async def test_launch_simulator_forbidden_for_viewer():
    """Verify that actors with 'viewer' role receive HTTP 403 Forbidden."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/simulator/run",
            headers={
                "x-actor-id": "auditor-1",
                "x-actor-role": "viewer",
            },
            json={
                "scenario": "normal",
                "team": "it-ops",
            },
        )
        assert response.status_code == 403
        assert "not permitted" in response.json()["detail"].lower() or "forbidden" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_launch_simulator_success_default_args():
    """Verify successful launch by operator with default arguments."""
    mock_proc = AsyncMock(spec=asyncio.subprocess.Process)
    mock_proc.communicate = AsyncMock(return_value=(b"output log", b""))
    mock_proc.returncode = 0

    with patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=mock_proc)) as mock_exec:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/simulator/run",
                headers={
                    "x-actor-id": "operator-1",
                    "x-actor-role": "operator",
                },
                json={
                    "scenario": "loop",
                },
            )

            assert response.status_code == 200
            data = response.json()
            assert data["scenario"] == "loop"
            assert data["team"] == "demo-sandbox"
            assert data["status"] == "LAUNCHED"
            assert data["run_id"].startswith("run_")

            # Verify subprocess call arguments
            mock_exec.assert_called_once()
            call_args, call_kwargs = mock_exec.call_args
            assert call_args[0] == sys.executable
            assert call_args[1:3] == ("-m", "sentinel_demo.runner")
            assert call_args[3:5] == ("--scenario", "loop")
            assert call_args[5] == "--run-id"
            assert call_args[6] == data["run_id"]
            assert call_args[7:9] == ("--team", "demo-sandbox")

            env = call_kwargs["env"]
            assert env["SENTINEL_URL"] == "http://127.0.0.1:8000"
            assert env["SENTINEL_API_KEY"] == settings.SENTINEL_API_KEY
            assert env["SENTINEL_LIVE_LLM"] == "false"


@pytest.mark.asyncio
async def test_launch_simulator_forces_demo_sandbox_team_and_live_llm():
    """Verify simulator forces team='demo-sandbox' and propagates live_llm flag."""
    mock_proc = AsyncMock(spec=asyncio.subprocess.Process)
    mock_proc.communicate = AsyncMock(return_value=(b"", b"error details"))
    mock_proc.returncode = 1

    with patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=mock_proc)) as mock_exec:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/simulator/run",
                headers={
                    "x-actor-id": "admin-1",
                    "x-actor-role": "admin",
                },
                json={
                    "scenario": "slow_loop",
                    "team": "secops",
                    "live_llm": True,
                },
            )

            assert response.status_code == 200
            data = response.json()
            assert data["scenario"] == "slow_loop"
            assert data["team"] == "demo-sandbox"
            assert data["status"] == "LAUNCHED"

            mock_exec.assert_called_once()
            _, call_kwargs = mock_exec.call_args
            env = call_kwargs["env"]
            assert env["SENTINEL_LIVE_LLM"] == "true"


@pytest.mark.asyncio
async def test_launch_simulator_forbidden_for_non_demo_org_user():
    """Verify regular organizational JWT users (is_demo=False) receive 403 Forbidden."""
    org_token = jwt.encode(
        {
            "sub": "usr_org_1",
            "email": "operator@acme.com",
            "name": "Org Operator",
            "role": "operator",
            "allowed_teams": ["it-ops"],
            "is_demo": False,
            "exp": datetime.now(UTC) + timedelta(minutes=30),
        },
        settings.JWT_SECRET,
        algorithm="HS256",
    )
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/simulator/run",
            headers={"Authorization": f"Bearer {org_token}"},
            json={"scenario": "normal", "team": "it-ops"},
        )
        assert response.status_code == 403


@pytest.mark.asyncio
async def test_launch_simulator_forbidden_when_demo_sandbox_disabled():
    """Verify simulator is blocked with 403 when ENABLE_DEMO_SANDBOX is False."""
    demo_token = jwt.encode(
        {
            "sub": "usr_approver",
            "email": "approver@sentinel.local",
            "name": "Demo Approver",
            "role": "approver",
            "allowed_teams": ["demo-sandbox"],
            "is_demo": True,
            "exp": datetime.now(UTC) + timedelta(minutes=30),
        },
        settings.JWT_SECRET,
        algorithm="HS256",
    )
    with patch.object(settings, "ENABLE_DEMO_SANDBOX", False):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/simulator/run",
                headers={"Authorization": f"Bearer {demo_token}"},
                json={"scenario": "normal"},
            )
            assert response.status_code == 403


@pytest.mark.asyncio
async def test_launch_simulator_windows_selector_loop_fallback():
    """Verify fallback to subprocess.Popen when create_subprocess_exec raises NotImplementedError (Windows SelectorEventLoop)."""
    from unittest.mock import MagicMock

    mock_popen = MagicMock()
    mock_popen.communicate.return_value = (b"output", b"")
    mock_popen.returncode = 0

    with (
        patch(
            "asyncio.create_subprocess_exec",
            side_effect=NotImplementedError("Windows selector loop"),
        ),
        patch("subprocess.Popen", return_value=mock_popen) as mock_popen_cls,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/simulator/run",
                headers={
                    "x-actor-id": "operator-1",
                    "x-actor-role": "operator",
                },
                json={"scenario": "normal"},
            )
            assert response.status_code == 200
            assert response.json()["status"] == "LAUNCHED"
            mock_popen_cls.assert_called_once()
            call_args, call_kwargs = mock_popen_cls.call_args
            assert call_args[0][0] == sys.executable
            assert call_args[0][1:3] == ["-m", "sentinel_demo.runner"]
            assert call_args[0][3:5] == ["--scenario", "normal"]
            assert call_kwargs["env"]["SENTINEL_URL"] == "http://127.0.0.1:8000"


@pytest.mark.asyncio
async def test_launch_simulator_invalid_scenario_validation_error():
    """Verify Pydantic validates allowed ScenarioName literals."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/simulator/run",
            headers={
                "x-actor-id": "operator-1",
                "x-actor-role": "operator",
            },
            json={
                "scenario": "invalid_scenario_name",
            },
        )
        assert response.status_code == 422

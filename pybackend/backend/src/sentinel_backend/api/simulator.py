import asyncio
import logging
import os
import subprocess
import sys
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status

from sentinel_backend.api.deps import ActorContext, get_current_actor
from sentinel_backend.config import settings
from sentinel_backend.schemas.simulator import (
    SimulatorLaunchRequest,
    SimulatorLaunchResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/simulator", tags=["simulator"])

_background_tasks: set[asyncio.Task[None]] = set()


def _log_process_result(
    returncode: int,
    stderr: bytes | None,
    run_id: str,
    scenario: str,
) -> None:
    if returncode != 0:
        stderr_text = (
            stderr.decode("utf-8", errors="replace").strip() if stderr else ""
        )
        logger.warning(
            "Simulator scenario '%s' (run_id=%s) exited with non-zero code %d: %s",
            scenario,
            run_id,
            returncode,
            stderr_text,
        )
    else:
        logger.info(
            "Simulator scenario '%s' (run_id=%s) finished successfully",
            scenario,
            run_id,
        )


async def _watch_asyncio_process(
    proc: asyncio.subprocess.Process,
    run_id: str,
    scenario: str,
) -> None:
    """Asynchronously monitor simulator asyncio subprocess and log non-zero exit or errors."""
    try:
        _stdout, stderr = await proc.communicate()
        _log_process_result(proc.returncode, stderr, run_id, scenario)
    except Exception:
        logger.exception(
            "Exception while monitoring simulator process (run_id=%s)",
            run_id,
        )


async def _watch_sync_process(
    proc: subprocess.Popen[bytes],
    run_id: str,
    scenario: str,
) -> None:
    """Monitor synchronous Popen subprocess in a worker thread (Windows SelectorEventLoop fallback)."""
    try:
        _stdout, stderr = await asyncio.to_thread(proc.communicate)
        _log_process_result(proc.returncode, stderr, run_id, scenario)
    except Exception:
        logger.exception(
            "Exception while monitoring simulator process (run_id=%s)",
            run_id,
        )


@router.post(
    "/run",
    response_model=SimulatorLaunchResponse,
    status_code=status.HTTP_200_OK,
)
async def launch_simulator_scenario(
    body: SimulatorLaunchRequest,
    actor: Annotated[ActorContext, Depends(get_current_actor)],
) -> SimulatorLaunchResponse:
    """Launch a simulated multi-agent chaos or demo scenario in the background."""
    if not (settings.ENABLE_DEMO_SANDBOX and actor.is_demo):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Simulator is only available in Demo Sandbox mode for demo sessions",
        )

    if actor.actor_role == "viewer":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Viewers are not permitted to launch simulation scenarios",
        )

    run_id = f"run_{uuid4().hex[:12]}"
    team = "demo-sandbox"

    env = os.environ.copy()
    env["SENTINEL_URL"] = "http://127.0.0.1:8000"
    env["SENTINEL_API_KEY"] = settings.SENTINEL_API_KEY
    env["SENTINEL_LIVE_LLM"] = "true" if body.live_llm else "false"
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"

    cmd = [
        sys.executable,
        "-m",
        "sentinel_demo.runner",
        "--scenario",
        body.scenario,
        "--run-id",
        run_id,
        "--team",
        team,
    ]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        task = asyncio.create_task(
            _watch_asyncio_process(proc, run_id, body.scenario)
        )
        _background_tasks.add(task)
        task.add_done_callback(_background_tasks.discard)
    except NotImplementedError:
        # Fallback for Windows SelectorEventLoop which does not implement subprocess transports
        sync_proc = await asyncio.to_thread(
            subprocess.Popen,
            cmd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        task = asyncio.create_task(
            _watch_sync_process(sync_proc, run_id, body.scenario)
        )
        _background_tasks.add(task)
        task.add_done_callback(_background_tasks.discard)

    return SimulatorLaunchResponse(
        run_id=run_id,
        scenario=body.scenario,
        team=team,
        status="LAUNCHED",
    )


__all__ = ["launch_simulator_scenario", "router"]

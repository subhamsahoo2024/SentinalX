import asyncio
import logging
from typing import Annotated, Any

from fastapi import (
    APIRouter,
    HTTPException,
    Query,
    WebSocket,
    WebSocketDisconnect,
    status,
)

from sentinel_backend.api.deps import (
    ActorContext,
    assert_team_access,
    decode_actor_from_token,
)
from sentinel_backend.config import settings
from sentinel_backend.services.redis_bus import subscribe_channel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ws", tags=["websocket"])


def _resolve_ws_actor(token: str | None) -> ActorContext | None:
    """Resolve ActorContext from ?token=<jwt> or sandbox fallback when enabled."""
    if token:
        try:
            return decode_actor_from_token(token.strip())
        except HTTPException:
            return None

    if settings.effective_allow_dev_headers:
        return ActorContext(
            actor_id="ws-demo",
            actor_role="viewer",
            allowed_teams=["demo-sandbox"],
            is_demo=True,
        )

    return None


def _extract_message_team(message: dict[str, Any]) -> str | None:
    """Extract team identifier from Redis pub/sub envelope or payload."""
    data = message.get("data")
    if isinstance(data, dict):
        team_val = data.get("team")
        if isinstance(team_val, str) and team_val:
            return team_val
    team_val = message.get("team")
    if isinstance(team_val, str) and team_val:
        return team_val
    return None


def _can_forward_message(message: dict[str, Any], actor: ActorContext) -> bool:
    """Return True only when the message's team passes assert_team_access."""
    team = _extract_message_team(message)
    if team is None:
        return False
    try:
        assert_team_access(team, actor)
        return True
    except HTTPException:
        return False


async def _stream_with_client_watchdog(
    websocket: WebSocket,
    channel: str,
    actor: ActorContext,
) -> None:
    """Stream team-scoped live events from Redis while detecting client disconnects."""
    await websocket.accept()

    async def _redis_sender() -> None:
        try:
            async for message in subscribe_channel(channel):
                if isinstance(message, dict) and _can_forward_message(
                    message, actor
                ):
                    await websocket.send_json(message)
        except WebSocketDisconnect:
            pass
        except Exception as e:  # noqa: BLE001
            logger.warning(
                "Error streaming Redis messages on channel %s: %s", channel, e
            )

    async def _client_receiver() -> None:
        try:
            while True:
                await websocket.receive()
        except WebSocketDisconnect:
            pass
        except Exception as e:  # noqa: BLE001
            logger.debug("WebSocket client receiver closed: %s", e)

    sender_task = asyncio.create_task(_redis_sender())
    receiver_task = asyncio.create_task(_client_receiver())

    _, pending = await asyncio.wait(
        [sender_task, receiver_task],
        return_when=asyncio.FIRST_COMPLETED,
    )
    for task in pending:
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, WebSocketDisconnect):
            pass


@router.websocket("/fleet")
async def ws_fleet(
    websocket: WebSocket,
    token: Annotated[str | None, Query()] = None,
) -> None:
    """Stream team-scoped fleet-wide events to connected WebSocket clients."""
    actor = _resolve_ws_actor(token)
    if actor is None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    await _stream_with_client_watchdog(websocket, "fleet:stream", actor)


@router.websocket("/runs/{run_id}")
async def ws_run(
    websocket: WebSocket,
    run_id: str,
    token: Annotated[str | None, Query()] = None,
) -> None:
    """Stream team-scoped live events for a specific run_id to WebSocket clients."""
    actor = _resolve_ws_actor(token)
    if actor is None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    await _stream_with_client_watchdog(websocket, f"run:{run_id}:stream", actor)


__all__ = ["router"]

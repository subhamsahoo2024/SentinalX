import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from sentinel_backend.services.redis_bus import subscribe_channel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ws", tags=["websocket"])


async def _stream_with_client_watchdog(websocket: WebSocket, channel: str) -> None:
    """Stream live events from a Redis channel while actively detecting client disconnects."""
    await websocket.accept()

    async def _redis_sender() -> None:
        try:
            async for message in subscribe_channel(channel):
                await websocket.send_json(message)
        except WebSocketDisconnect:
            pass
        except Exception as e:
            logger.warning(
                "Error streaming Redis messages on channel %s: %s", channel, e
            )

    async def _client_receiver() -> None:
        try:
            while True:
                await websocket.receive()
        except WebSocketDisconnect:
            pass
        except Exception:
            pass

    sender_task = asyncio.create_task(_redis_sender())
    receiver_task = asyncio.create_task(_client_receiver())

    done, pending = await asyncio.wait(
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
async def ws_fleet(websocket: WebSocket) -> None:
    """Stream fleet-wide events to connected WebSocket clients."""
    await _stream_with_client_watchdog(websocket, "fleet:stream")


@router.websocket("/runs/{run_id}")
async def ws_run(websocket: WebSocket, run_id: str) -> None:
    """Stream live events for a specific run_id to connected WebSocket clients."""
    await _stream_with_client_watchdog(websocket, f"run:{run_id}:stream")


__all__ = ["router"]

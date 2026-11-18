import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from sentinel_backend.services.redis_bus import subscribe_channel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ws", tags=["websocket"])


@router.websocket("/fleet")
async def ws_fleet(websocket: WebSocket) -> None:
    """Stream fleet-wide events to connected WebSocket clients."""
    await websocket.accept()
    try:
        async for message in subscribe_channel("fleet:stream"):
            await websocket.send_json(message)
    except WebSocketDisconnect:
        logger.debug("Fleet WebSocket client disconnected")
    except Exception as e:
        logger.warning("Error in /ws/fleet stream: %s", e)


@router.websocket("/runs/{run_id}")
async def ws_run(websocket: WebSocket, run_id: str) -> None:
    """Stream live events for a specific run_id to connected WebSocket clients."""
    await websocket.accept()
    channel = f"run:{run_id}:stream"
    try:
        async for message in subscribe_channel(channel):
            await websocket.send_json(message)
    except WebSocketDisconnect:
        logger.debug("Run WebSocket client disconnected for run %s", run_id)
    except Exception as e:
        logger.warning("Error in /ws/runs/%s stream: %s", run_id, e)


__all__ = ["router"]


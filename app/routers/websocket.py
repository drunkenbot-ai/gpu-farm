"""Dashboard WebSocket endpoint for real-time worker/job/telemetry push."""

from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.ws import manager as ws_manager

router = APIRouter(tags=["ws"])


@router.websocket("/ws")
async def dashboard_socket(websocket: WebSocket) -> None:
    """Accept a dashboard client and keep it registered until it disconnects."""

    await ws_manager.connect(websocket)
    try:
        while True:
            # Dashboard clients are push-only consumers; drain any client
            # pings/keepalives without acting on them.
            await websocket.receive_text()
    except WebSocketDisconnect:
        await ws_manager.disconnect(websocket)

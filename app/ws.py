"""WebSocket broadcast hub for real-time farm state (goals.md dashboard reqs)."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import WebSocket


class ConnectionManager:
    """Tracks connected dashboard clients and broadcasts JSON events."""

    def __init__(self) -> None:
        """Create an empty connection manager."""

        self._connections: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket) -> None:
        """Accept and register a dashboard WebSocket connection."""

        await websocket.accept()
        async with self._lock:
            self._connections.add(websocket)

    async def disconnect(self, websocket: WebSocket) -> None:
        """Remove a disconnected WebSocket connection."""

        async with self._lock:
            self._connections.discard(websocket)

    async def broadcast(self, event: dict[str, Any]) -> None:
        """Send a JSON event to every connected dashboard client.

        Args:
            event: JSON-serializable event payload, e.g.
                `{"type": "worker_update", "worker": {...}}`.
        """

        async with self._lock:
            targets = list(self._connections)
        for websocket in targets:
            try:
                await websocket.send_json(event)
            except Exception:
                await self.disconnect(websocket)


manager = ConnectionManager()

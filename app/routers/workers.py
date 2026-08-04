"""Worker registration/heartbeat routes.

Thin FastAPI wrapper around `engine.coordinator.JobManager` -- the actual
register/heartbeat/stale-worker logic lives in the `engine` submodule and is
shared with LLM-IDE's own coordinator. This layer adds: cloud entitlement
gating and WebSocket broadcast of state changes.
"""

from __future__ import annotations

from typing import Any, Optional

from engine.contracts import HeartbeatRequest, RegisterWorkerRequest
from fastapi import APIRouter, Body, Depends, Header, HTTPException

from app.cloud_entitlement import validate_cloud_api_key
from app.config import Settings, get_settings
from app.job_manager import get_job_manager
from app.ws import manager as ws_manager

router = APIRouter(tags=["workers"])


async def require_farm_entitlement(
    settings: Settings = Depends(get_settings),
    authorization: str = Header(default=""),
) -> None:
    """Gate cloud-pool access on a valid cloud-service API key.

    No-op for `FARM_MODE=local` (goals.md section 9: local workflow must
    never contact the licensing service). In `FARM_MODE=cloud`, requires a
    `Bearer <api_key>` header validated via cloud-service `/auth/validate-key`.
    """

    if settings.farm_mode != "cloud":
        return
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing cloud GPU-hours API key.")
    api_key = authorization.removeprefix("Bearer ").strip()
    result = await validate_cloud_api_key(api_key, settings)
    if not result.valid:
        raise HTTPException(status_code=403, detail=result.reason or "Invalid cloud entitlement.")


@router.get("/workers")
def list_workers(manager=Depends(get_job_manager)) -> dict[str, Any]:
    """List all registered workers."""

    return {"workers": [worker.to_jsonable() for worker in manager.list_workers()]}


@router.post("/register", dependencies=[Depends(require_farm_entitlement)])
async def register_worker(payload: dict[str, Any] = Body(...), manager=Depends(get_job_manager)) -> dict[str, Any]:
    """Register a worker (local machine or remote worker client)."""

    response = manager.register_remote_worker(RegisterWorkerRequest.from_jsonable(payload))
    await ws_manager.broadcast({"type": "worker_registered", "worker_id": payload.get("worker_id")})
    return response.to_jsonable()


@router.post("/heartbeat")
async def heartbeat(payload: dict[str, Any] = Body(...), manager=Depends(get_job_manager)) -> dict[str, Any]:
    """Handle a worker heartbeat and broadcast the update to dashboards."""

    response = manager.handle_heartbeat(HeartbeatRequest.from_jsonable(payload))
    await ws_manager.broadcast({"type": "worker_heartbeat", "worker_id": payload.get("worker_id")})
    return response.to_jsonable()


@router.post("/stale-workers")
def stale_workers(
    timeout_seconds: Optional[int] = None,
    settings: Settings = Depends(get_settings),
    manager=Depends(get_job_manager),
) -> dict[str, Any]:
    """Mark workers offline that have not sent a heartbeat recently."""

    timeout = timeout_seconds if timeout_seconds is not None else settings.stale_worker_timeout_seconds
    return {"offline_workers": manager.mark_stale_workers_offline(timeout_seconds=timeout)}

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
from app.gpu_discovery import GpuInfo, validate_gpu
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
    """Register a worker (local machine or remote worker client).

    Enforces goals.md section 3: "Only validated GPUs can participate in
    the farm." Workers self-report detected GPUs under
    `capabilities.extra.gpus` (see `app/gpu_discovery.py`); registration is
    rejected outright when none of the reported GPUs pass validation.
    Workers that report no GPUs at all (e.g. CPU-only local dev use) are
    still accepted -- goals.md scopes the *validation* requirement to GPUs
    that intend to join the farm as trainable resources, not to whether a
    machine has a GPU at all.
    """

    worker_id = str(payload.get("worker_id", ""))
    reported_gpus = ((payload.get("capabilities") or {}).get("extra") or {}).get("gpus") or []
    if reported_gpus:
        validations = [validate_gpu(_gpu_info_from_jsonable(entry)) for entry in reported_gpus]
        if not any(result.valid for result in validations):
            reasons = [reason for result in validations for reason in result.reasons]
            raise HTTPException(
                status_code=422,
                detail=f"No validated GPU on worker '{worker_id}': {'; '.join(reasons) or 'all reported GPUs failed validation.'}",
            )

    response = manager.register_remote_worker(RegisterWorkerRequest.from_jsonable(payload))
    await ws_manager.broadcast({"type": "worker_registered", "worker_id": worker_id})
    return response.to_jsonable()


def _gpu_info_from_jsonable(entry: dict[str, Any]) -> GpuInfo:
    """Rebuild a `GpuInfo` from a worker-reported GPU dict for validation."""

    return GpuInfo(
        index=int(entry.get("index", 0)),
        name=str(entry.get("name", "unknown")),
        vendor=str(entry.get("vendor", "NVIDIA")),
        uuid=entry.get("uuid"),
        vram_total_mb=entry.get("vram_total_mb"),
        vram_free_mb=entry.get("vram_free_mb"),
        vram_used_mb=entry.get("vram_used_mb"),
        utilization_percent=entry.get("utilization_percent"),
        temperature_c=entry.get("temperature_c"),
        power_watts=entry.get("power_watts"),
        driver_version=entry.get("driver_version"),
        pci_id=entry.get("pci_id"),
        compute_capability=entry.get("compute_capability"),
        cuda_version=entry.get("cuda_version"),
        cuda_supported=bool(entry.get("cuda_supported", False)),
        source=str(entry.get("source", "reported")),
    )


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

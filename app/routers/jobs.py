"""Training job routes: submit/claim/progress/complete/fail + farm-wide job controls.

Wraps `engine.coordinator.JobManager`; see `app/routers/workers.py` for the
shared design notes. Scheduling considerations beyond the engine's own
backend/VRAM/tag matching (resource pools, live CPU/RAM/disk/GPU
utilization, local-vs-cloud mode, cloud entitlement) live in
`app/scheduler.py` and are applied here at submission and claim time.
"""

from __future__ import annotations

from typing import Any, Optional
from uuid import uuid4

from engine.contracts import (
    BackendKind,
    ClaimJobRequest,
    CompleteJobRequest,
    FailJobRequest,
    ProgressReportRequest,
    TrainingJobSpec,
)
from fastapi import APIRouter, Body, Depends, Header, HTTPException

from app.cloud_entitlement import release_cloud_reservation, reserve_cloud_usage, validate_cloud_api_key
from app.config import Settings, get_settings
from app.job_manager import get_job_manager
from app.pools import PoolStore, get_pool_store
from app.scheduler import SchedulingRequirements, evaluate_all_workers, resource_health
from app.tagging import TagStore, get_tag_store
from app.ws import manager as ws_manager
from app.telemetry import record
from app.cloud_usage import complete as complete_cloud_usage, start as start_cloud_usage
from app.security import require_operator
from engine.coordinator.artifacts import create_job_artifact_bundle, create_job_project_tree

router = APIRouter(tags=["jobs"])


@router.get("/jobs")
def list_jobs(manager=Depends(get_job_manager)) -> dict[str, Any]:
    """List all known training jobs."""

    return {"jobs": [job.to_jsonable() for job in manager.list_jobs()]}


@router.get("/jobs/schedule-preview")
def schedule_preview(
    backend: str = "local",
    min_vram_gb: Optional[float] = None,
    resource_pool_id: Optional[str] = None,
    manager=Depends(get_job_manager),
    settings: Settings = Depends(get_settings),
    pool_store: PoolStore = Depends(get_pool_store),
    tag_store: TagStore = Depends(get_tag_store),
) -> dict[str, Any]:
    """Dry-run the scheduler for hypothetical requirements.

    Shows, for every known worker, whether it is currently eligible to run
    a job with these requirements and why not if it isn't -- lets the
    dashboard surface over-allocation / pool-emptiness before a project is
    actually submitted.
    """

    requirements = SchedulingRequirements(backend=backend, min_vram_gb=min_vram_gb, resource_pool_id=resource_pool_id)
    results = evaluate_all_workers(requirements, manager, settings, pool_store, tag_store)
    return {"requirements": requirements.__dict__, "workers": [r.to_jsonable() for r in results]}


@router.post("/jobs", dependencies=[Depends(require_operator)])
async def submit_job(
    payload: dict[str, Any] = Body(...),
    authorization: str = Header(default=""),
    manager=Depends(get_job_manager),
    settings: Settings = Depends(get_settings),
    pool_store: PoolStore = Depends(get_pool_store),
    tag_store: TagStore = Depends(get_tag_store),
) -> dict[str, Any]:
    """Submit a new training job to the farm queue.

    Args:
        payload: `{"job": <TrainingJobSpec.to_jsonable() shaped dict>,
            "resource_pool_id": str?}`. `job.runtime.backend` selects local
            vs cloud vs remote-client execution (goals.md sections 9-10);
            cloud jobs require a valid `Authorization: Bearer <api_key>`
            when `FARM_MODE=cloud`, mirroring worker registration.

    The job is queued as usual (workers still pull it via `/claim-job`).
    When `resource_pool_id` is given and currently resolves to exactly one
    eligible worker, that worker is pinned via `runtime.preferred_worker_id`;
    with zero or multiple eligible members the pool is recorded in
    `metadata.resource_pool_id` for visibility but left as an advisory
    hint, since the engine's claim matcher only supports a single pinned
    worker per job today.
    """

    job_data = payload.get("job")
    if not job_data:
        raise HTTPException(status_code=400, detail="payload.job is required.")
    try:
        job = TrainingJobSpec.from_jsonable(job_data)
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"Invalid job spec: {exc}") from exc

    cloud_api_key: str | None = None
    if job.runtime.backend == BackendKind.CLOUD and settings.farm_mode == "cloud":
        if not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Missing cloud GPU-hours API key.")
        result = await validate_cloud_api_key(authorization.removeprefix("Bearer ").strip(), settings)
        if not result.valid:
            raise HTTPException(status_code=403, detail=result.reason or "Invalid cloud entitlement.")
        job.metadata["cloud_account_id"] = result.account_id
        job.metadata["cloud_quota_gpu_hours"] = result.quota_gpu_hours_per_month
        try:
            reserved_hours = float(payload.get("estimated_gpu_hours", job.metadata.get("estimated_gpu_hours", 1.0)))
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail="estimated_gpu_hours must be a positive number.") from exc
        if reserved_hours <= 0:
            raise HTTPException(status_code=400, detail="estimated_gpu_hours must be greater than zero.")
        cloud_api_key = authorization.removeprefix("Bearer ").strip()
        job.metadata["cloud_reservation_gpu_hours"] = reserved_hours

    resource_pool_id = payload.get("resource_pool_id")
    if resource_pool_id:
        job.metadata["resource_pool_id"] = resource_pool_id
        requirements = SchedulingRequirements(
            backend=job.runtime.backend.value,
            min_vram_gb=job.runtime.min_vram_gb,
            resource_pool_id=resource_pool_id,
            tags=job.runtime.tags,
        )
        eligibility = evaluate_all_workers(requirements, manager, settings, pool_store, tag_store)
        eligible_ids = [e.worker_id for e in eligibility if e.eligible]
        job.metadata["scheduler_eligible_worker_ids"] = eligible_ids
        if len(eligible_ids) == 1:
            job.runtime.preferred_worker_id = eligible_ids[0]

    try:
        create_job_project_tree(job, artifact_root=settings.artifact_root)
        create_job_artifact_bundle(job, artifact_root=settings.artifact_root)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if cloud_api_key:
        accepted, reason = await reserve_cloud_usage(
            cloud_api_key,
            {"job_id": job.job_id, "gpu_hours": job.metadata["cloud_reservation_gpu_hours"], "gpu_count": 1},
            settings,
        )
        if not accepted:
            raise HTTPException(status_code=403, detail=reason or "Cloud GPU-hours quota reservation was rejected.")
    job_id = manager.submit(job)
    await ws_manager.broadcast({"type": "job_submitted", "job_id": job_id})
    return {"job_id": job_id, "job": manager.get_job(job_id).spec.to_jsonable()}


@router.post("/claim-job")
async def claim_job(
    payload: dict[str, Any] = Body(...),
    manager=Depends(get_job_manager),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """Let an available worker claim the next eligible queued job.

    Applies the scheduler's live resource-health gate (goals.md: "Prevent
    resource over-allocation") first: a worker that is nominally
    'available' but reports CPU/RAM/disk/GPU utilization already past the
    configured thresholds in this same claim request is told there's no
    job for it, without ever consulting -- or mutating -- the engine's
    queue.
    """

    capabilities = payload.get("capabilities") or {}
    saturation_reasons = resource_health(capabilities, settings)
    if saturation_reasons:
        return {
            "status": "ok",
            "job": None,
            "message": f"worker resource-constrained: {'; '.join(saturation_reasons)}",
        }

    response = manager.handle_claim_job(ClaimJobRequest.from_jsonable(payload))
    await ws_manager.broadcast({"type": "job_claimed", "worker_id": payload.get("worker_id")})
    return response.to_jsonable()


@router.post("/progress")
async def report_progress(payload: dict[str, Any] = Body(...), manager=Depends(get_job_manager)) -> dict[str, Any]:
    """Record a training progress update and broadcast it live."""

    response = manager.handle_progress_report(ProgressReportRequest.from_jsonable(payload))
    try:
        job = manager.get_job(str(payload.get("job_id"))).spec
        if job.runtime.backend == BackendKind.CLOUD and job.metadata.get("cloud_account_id"):
            start_cloud_usage(job.job_id, str(job.metadata["cloud_account_id"]))
    except KeyError:
        pass
    record(str(payload.get("worker_id", "unknown")), "progress", dict(payload.get("metrics") or {}))
    await ws_manager.broadcast({"type": "job_progress", "job_id": payload.get("job_id"), "metrics": payload.get("metrics")})
    return response.to_jsonable()


@router.post("/complete")
async def complete_job(payload: dict[str, Any] = Body(...), manager=Depends(get_job_manager)) -> dict[str, Any]:
    """Mark a job complete and broadcast the result."""

    response = manager.handle_complete_job(CompleteJobRequest.from_jsonable(payload))
    result_data = payload.get("result") or {}
    complete_cloud_usage(str(result_data.get("job_id", "")))
    await ws_manager.broadcast({"type": "job_completed", "job_id": payload.get("job_id")})
    return response.to_jsonable()


@router.post("/fail")
async def fail_job(payload: dict[str, Any] = Body(...), authorization: str = Header(default=""), manager=Depends(get_job_manager), settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    """Mark a job failed and broadcast the failure."""

    response = manager.handle_fail_job(FailJobRequest.from_jsonable(payload))
    await _release_cloud_hold(str(payload.get("job_id", "")), authorization, manager, settings)
    await ws_manager.broadcast({"type": "job_failed", "job_id": payload.get("job_id")})
    return response.to_jsonable()


@router.post("/pause-all", dependencies=[Depends(require_operator)])
def pause_all(manager=Depends(get_job_manager)) -> dict[str, Any]:
    """Pause every running job."""

    return {"paused": manager.pause_all_jobs()}


@router.post("/resume-all", dependencies=[Depends(require_operator)])
def resume_all(manager=Depends(get_job_manager)) -> dict[str, Any]:
    """Resume every paused job."""

    return {"resumed": manager.resume_all_jobs()}


@router.post("/stop-all", dependencies=[Depends(require_operator)])
def stop_all(manager=Depends(get_job_manager)) -> dict[str, Any]:
    """Stop every running/queued job."""

    return {"stopping": manager.stop_all_jobs()}


@router.post("/jobs/{job_id}/cancel", dependencies=[Depends(require_operator)])
async def cancel_job(job_id: str, authorization: str = Header(default=""), manager=Depends(get_job_manager), settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    """Cooperatively cancel one queued or running job."""
    try: manager.cancel(job_id)
    except KeyError as exc: raise HTTPException(404, "Job not found") from exc
    await _release_cloud_hold(job_id, authorization, manager, settings)
    await ws_manager.broadcast({"type": "job_stopping", "job_id": job_id})
    return {"job_id": job_id, "status": "stopping"}


@router.post("/jobs/{job_id}/pause", dependencies=[Depends(require_operator)])
async def pause_job(job_id: str, manager=Depends(get_job_manager)) -> dict[str, Any]:
    try: managed = manager.get_job(job_id)
    except KeyError as exc: raise HTTPException(404, "Job not found") from exc
    if managed.spec.status.value not in {"queued", "assigned", "running"}: raise HTTPException(409, "Job cannot be paused in its current state.")
    managed.spec.status = managed.spec.status.PAUSED; manager._persist_job(job_id)
    await ws_manager.broadcast({"type": "job_paused", "job_id": job_id})
    return {"job_id": job_id, "status": "paused"}


@router.post("/jobs/{job_id}/resume", dependencies=[Depends(require_operator)])
async def resume_job(job_id: str, manager=Depends(get_job_manager)) -> dict[str, Any]:
    try: managed = manager.get_job(job_id)
    except KeyError as exc: raise HTTPException(404, "Job not found") from exc
    if managed.spec.status.value != "paused": raise HTTPException(409, "Job is not paused.")
    managed.spec.status = managed.spec.status.QUEUED; managed.assigned_worker_id = None; manager._persist_job(job_id)
    await ws_manager.broadcast({"type": "job_resumed", "job_id": job_id})
    return {"job_id": job_id, "status": "queued"}


@router.post("/jobs/{job_id}/restart", dependencies=[Depends(require_operator)])
async def restart_job(job_id: str, settings: Settings = Depends(get_settings), manager=Depends(get_job_manager)) -> dict[str, Any]:
    """Clone a completed/failed job into a fresh queued attempt."""
    try: original = manager.get_job(job_id).spec
    except KeyError as exc: raise HTTPException(404, "Job not found") from exc
    clone = TrainingJobSpec.from_jsonable(original.to_jsonable()); clone.job_id = f"job_{uuid4().hex}"; clone.status = clone.status.QUEUED
    clone.metadata = {**clone.metadata, "restarted_from_job_id": job_id}
    create_job_project_tree(clone, artifact_root=settings.artifact_root); create_job_artifact_bundle(clone, artifact_root=settings.artifact_root)
    manager.submit(clone)
    await ws_manager.broadcast({"type": "job_restarted", "job_id": clone.job_id, "restarted_from_job_id": job_id})
    return {"job_id": clone.job_id, "restarted_from_job_id": job_id}


async def _release_cloud_hold(job_id: str, authorization: str, manager, settings: Settings) -> None:
    """Best-effort release. API keys are deliberately never persisted by the manager."""
    if not authorization.startswith("Bearer "):
        return
    try:
        job = manager.get_job(job_id).spec
    except KeyError:
        return
    hours = job.metadata.get("cloud_reservation_gpu_hours")
    if job.runtime.backend != BackendKind.CLOUD or not hours:
        return
    await release_cloud_reservation(
        authorization.removeprefix("Bearer ").strip(),
        {"job_id": job_id, "gpu_hours": hours, "gpu_count": 1},
        settings,
    )

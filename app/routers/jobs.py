"""Training job routes: claim/progress/complete/fail + farm-wide job controls.

Wraps `engine.coordinator.JobManager`; see `app/routers/workers.py` for the
shared design notes.
"""

from __future__ import annotations

from typing import Any

from engine.contracts import (
    ClaimJobRequest,
    CompleteJobRequest,
    FailJobRequest,
    ProgressReportRequest,
)
from fastapi import APIRouter, Body, Depends

from app.job_manager import get_job_manager
from app.ws import manager as ws_manager

router = APIRouter(tags=["jobs"])


@router.get("/jobs")
def list_jobs(manager=Depends(get_job_manager)) -> dict[str, Any]:
    """List all known training jobs."""

    return {"jobs": [job.to_jsonable() for job in manager.list_jobs()]}


@router.post("/claim-job")
async def claim_job(payload: dict[str, Any] = Body(...), manager=Depends(get_job_manager)) -> dict[str, Any]:
    """Let an available worker claim the next eligible queued job."""

    response = manager.handle_claim_job(ClaimJobRequest.from_jsonable(payload))
    await ws_manager.broadcast({"type": "job_claimed", "worker_id": payload.get("worker_id")})
    return response.to_jsonable()


@router.post("/progress")
async def report_progress(payload: dict[str, Any] = Body(...), manager=Depends(get_job_manager)) -> dict[str, Any]:
    """Record a training progress update and broadcast it live."""

    response = manager.handle_progress_report(ProgressReportRequest.from_jsonable(payload))
    await ws_manager.broadcast({"type": "job_progress", "job_id": payload.get("job_id"), "metrics": payload.get("metrics")})
    return response.to_jsonable()


@router.post("/complete")
async def complete_job(payload: dict[str, Any] = Body(...), manager=Depends(get_job_manager)) -> dict[str, Any]:
    """Mark a job complete and broadcast the result."""

    response = manager.handle_complete_job(CompleteJobRequest.from_jsonable(payload))
    await ws_manager.broadcast({"type": "job_completed", "job_id": payload.get("job_id")})
    return response.to_jsonable()


@router.post("/fail")
async def fail_job(payload: dict[str, Any] = Body(...), manager=Depends(get_job_manager)) -> dict[str, Any]:
    """Mark a job failed and broadcast the failure."""

    response = manager.handle_fail_job(FailJobRequest.from_jsonable(payload))
    await ws_manager.broadcast({"type": "job_failed", "job_id": payload.get("job_id")})
    return response.to_jsonable()


@router.post("/pause-all")
def pause_all(manager=Depends(get_job_manager)) -> dict[str, Any]:
    """Pause every running job."""

    return {"paused": manager.pause_all_jobs()}


@router.post("/resume-all")
def resume_all(manager=Depends(get_job_manager)) -> dict[str, Any]:
    """Resume every paused job."""

    return {"resumed": manager.resume_all_jobs()}


@router.post("/stop-all")
def stop_all(manager=Depends(get_job_manager)) -> dict[str, Any]:
    """Stop every running/queued job."""

    return {"stopping": manager.stop_all_jobs()}

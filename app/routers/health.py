"""Health/farm-summary endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.config import Settings, get_settings
from app.job_manager import get_job_manager

router = APIRouter(tags=["health"])


@router.get("/health")
def health(settings: Settings = Depends(get_settings), manager=Depends(get_job_manager)) -> dict:
    """Return farm health/summary for the dashboard header.

    Returns:
        Basic status payload: mode, worker count, job count.
    """

    return {
        "status": "ok",
        "farm_mode": settings.farm_mode,
        "workers": len(manager.list_workers()),
        "jobs": len(manager.list_jobs()),
    }

from __future__ import annotations

from fastapi import APIRouter, Query
from app.telemetry import history

router = APIRouter(prefix="/monitoring", tags=["monitoring"])

@router.get("/history")
def telemetry_history(worker_id: str | None = None, kind: str | None = None, limit: int = Query(500, ge=1, le=10000)) -> dict:
    return {"samples": history(worker_id, kind, limit)}

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from app.audit_log import history
from app.security import require_operator

router = APIRouter(prefix="/audit", tags=["audit"], dependencies=[Depends(require_operator)])

@router.get("")
def audit_history(limit: int = Query(500, ge=1, le=10000)) -> dict:
    """Return Farm Manager administrative mutation history."""
    return {"events": history(limit)}

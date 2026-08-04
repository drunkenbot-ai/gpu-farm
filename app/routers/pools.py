"""Resource Pools & Tagging (goals.md sections 7-8).

Placeholder for Phase 4. Not implemented yet -- Farm Manager currently
schedules on raw workers only. Kept as a stub router so the API surface and
frontend can be wired against a stable path ahead of the real
implementation (pool CRUD, rule-based membership, tag assignment).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/pools", tags=["pools"])


@router.get("")
def list_pools() -> dict:
    """Return configured resource pools.

    Returns:
        Empty list until Phase 4 (pool storage/model) lands.
    """

    return {"pools": []}


@router.post("")
def create_pool() -> None:
    """Create a resource pool.

    Raises:
        HTTPException: Always, until Phase 4 implements pool storage.
    """

    raise HTTPException(status_code=501, detail="Resource pools are not implemented yet (plan phase 4).")

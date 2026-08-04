"""Resource Pools & Tagging routes (goals.md sections 7-8).

Resource Pools group GPUs from anywhere in the farm -- manually selected,
matched by rule (vendor, model, compute capability, VRAM size, driver
version, machine, tags), or both -- so projects can target a pool instead
of pinning a specific GPU (goals.md: "Projects should target Resource
Pools rather than specific GPUs").
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException

from app.gpu_inventory import build_inventory
from app.job_manager import get_job_manager
from app.pools import PoolRule, PoolStore, get_pool_store, pool_stats, resolve_members
from app.tagging import TagStore, get_tag_store

router = APIRouter(prefix="/pools", tags=["pools"])


def _pool_view(pool, manager, tag_store: TagStore) -> dict[str, Any]:
    """Build the API view of a pool: its definition plus resolved stats."""

    inventory = build_inventory(manager, tag_store)
    members = resolve_members(pool, inventory)
    data = pool.to_jsonable()
    data["stats"] = pool_stats(members, pool)
    data["gpus"] = [m.to_jsonable() for m in members]
    return data


@router.get("")
def list_pools(
    manager=Depends(get_job_manager),
    store: PoolStore = Depends(get_pool_store),
    tag_store: TagStore = Depends(get_tag_store),
) -> dict[str, Any]:
    """List every configured Resource Pool with live membership stats."""

    return {"pools": [_pool_view(pool, manager, tag_store) for pool in store.list_pools()]}


@router.post("")
def create_pool(
    payload: dict[str, Any] = Body(...),
    manager=Depends(get_job_manager),
    store: PoolStore = Depends(get_pool_store),
    tag_store: TagStore = Depends(get_tag_store),
) -> dict[str, Any]:
    """Create a Resource Pool.

    Args:
        payload: `{"name": str, "description": str?, "rules": [{"field":,
            "op":, "value":}, ...]?, "manual_members": ["worker_id::identifier",
            ...]?, "assigned_projects": [str, ...]?}`.
    """

    name = str(payload.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Pool name is required.")
    rules = [PoolRule.from_jsonable(r) for r in payload.get("rules") or []]
    pool = store.create_pool(
        name=name,
        description=str(payload.get("description") or ""),
        rules=rules,
        manual_members=list(payload.get("manual_members") or []),
        assigned_projects=list(payload.get("assigned_projects") or []),
    )
    return _pool_view(pool, manager, tag_store)


@router.get("/{pool_id}")
def get_pool(
    pool_id: str,
    manager=Depends(get_job_manager),
    store: PoolStore = Depends(get_pool_store),
    tag_store: TagStore = Depends(get_tag_store),
) -> dict[str, Any]:
    """Return one pool with its resolved membership and stats."""

    pool = store.get_pool(pool_id)
    if pool is None:
        raise HTTPException(status_code=404, detail=f"Unknown pool: {pool_id}")
    return _pool_view(pool, manager, tag_store)


@router.put("/{pool_id}")
def update_pool(
    pool_id: str,
    payload: dict[str, Any] = Body(...),
    manager=Depends(get_job_manager),
    store: PoolStore = Depends(get_pool_store),
    tag_store: TagStore = Depends(get_tag_store),
) -> dict[str, Any]:
    """Edit, rename, re-rule, or enable/disable a pool.

    Args:
        payload: Any subset of `name`, `description`, `enabled`, `rules`,
            `manual_members`, `assigned_projects`.
    """

    changes: dict[str, Any] = {}
    for key in ("name", "description", "enabled", "rules", "manual_members", "assigned_projects"):
        if key in payload:
            changes[key] = payload[key]
    pool = store.update_pool(pool_id, **changes)
    if pool is None:
        raise HTTPException(status_code=404, detail=f"Unknown pool: {pool_id}")
    return _pool_view(pool, manager, tag_store)


@router.delete("/{pool_id}")
def delete_pool(pool_id: str, store: PoolStore = Depends(get_pool_store)) -> dict[str, Any]:
    """Delete a pool."""

    if not store.delete_pool(pool_id):
        raise HTTPException(status_code=404, detail=f"Unknown pool: {pool_id}")
    return {"deleted": pool_id}


@router.post("/{pool_id}/members")
def add_member(
    pool_id: str,
    payload: dict[str, Any] = Body(...),
    manager=Depends(get_job_manager),
    store: PoolStore = Depends(get_pool_store),
    tag_store: TagStore = Depends(get_tag_store),
) -> dict[str, Any]:
    """Manually add one GPU to a pool.

    Args:
        payload: `{"worker_id": str, "identifier": str}` -- identifier as
            returned by `GET /gpu-discovery/{worker_id}/selection` or in a
            pool's `gpus[].identifier`.
    """

    worker_id = str(payload.get("worker_id") or "")
    identifier = str(payload.get("identifier") or "")
    if not worker_id or not identifier:
        raise HTTPException(status_code=400, detail="worker_id and identifier are required.")
    pool = store.add_manual_member(pool_id, worker_id, identifier)
    if pool is None:
        raise HTTPException(status_code=404, detail=f"Unknown pool: {pool_id}")
    return _pool_view(pool, manager, tag_store)


@router.delete("/{pool_id}/members/{worker_id}/{identifier}")
def remove_member(
    pool_id: str,
    worker_id: str,
    identifier: str,
    manager=Depends(get_job_manager),
    store: PoolStore = Depends(get_pool_store),
    tag_store: TagStore = Depends(get_tag_store),
) -> dict[str, Any]:
    """Manually remove one GPU from a pool.

    Note this only removes the *manual* membership grant -- a GPU that
    still matches the pool's rules remains a member (goals.md pools can
    combine manual selection with rule-based membership).
    """

    pool = store.remove_manual_member(pool_id, worker_id, identifier)
    if pool is None:
        raise HTTPException(status_code=404, detail=f"Unknown pool: {pool_id}")
    return _pool_view(pool, manager, tag_store)

"""Tagging routes (goals.md section 8: "Tagging System").

Every worker and GPU supports metadata tags, usable for Resource Pool
membership, scheduling, filtering, and search. `GET /tags` returns the full
farm inventory with each GPU's combined auto + manual tags so the dashboard
can drive pool rule-builders and search from one place.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException

from app.gpu_inventory import build_inventory
from app.job_manager import get_job_manager
from app.tagging import TagStore, get_tag_store, gpu_scope, worker_scope

router = APIRouter(prefix="/tags", tags=["tags"])


@router.get("")
def list_tagged_inventory(
    manager=Depends(get_job_manager),
    tag_store: TagStore = Depends(get_tag_store),
) -> dict[str, Any]:
    """Return every farm GPU with its combined auto + manual tags."""

    return {"gpus": [entry.to_jsonable() for entry in build_inventory(manager, tag_store)]}


@router.get("/workers/{worker_id}")
def get_worker_tags(worker_id: str, tag_store: TagStore = Depends(get_tag_store)) -> dict[str, Any]:
    """Return the manually-assigned tags for a whole worker."""

    return {"worker_id": worker_id, "tags": tag_store.get_tags(worker_scope(worker_id))}


@router.put("/workers/{worker_id}")
def set_worker_tags(
    worker_id: str,
    payload: dict[str, Any] = Body(...),
    tag_store: TagStore = Depends(get_tag_store),
) -> dict[str, Any]:
    """Persist the manual tags for a whole worker.

    Args:
        worker_id: Worker identifier.
        payload: `{"tags": [str, ...]}`.
    """

    tags = tag_store.set_tags(worker_scope(worker_id), list(payload.get("tags") or []))
    return {"worker_id": worker_id, "tags": tags}


@router.get("/workers/{worker_id}/gpus/{identifier}")
def get_gpu_tags(worker_id: str, identifier: str, tag_store: TagStore = Depends(get_tag_store)) -> dict[str, Any]:
    """Return the manually-assigned tags for one GPU."""

    return {
        "worker_id": worker_id,
        "identifier": identifier,
        "tags": tag_store.get_tags(gpu_scope(worker_id, identifier)),
    }


@router.put("/workers/{worker_id}/gpus/{identifier}")
def set_gpu_tags(
    worker_id: str,
    identifier: str,
    payload: dict[str, Any] = Body(...),
    tag_store: TagStore = Depends(get_tag_store),
) -> dict[str, Any]:
    """Persist the manual tags for one GPU.

    Args:
        worker_id: Worker identifier.
        identifier: Stable GPU identifier (see `gpu_selection.gpu_identifier`).
        payload: `{"tags": [str, ...]}`.
    """

    tags = tag_store.set_tags(gpu_scope(worker_id, identifier), list(payload.get("tags") or []))
    return {"worker_id": worker_id, "identifier": identifier, "tags": tags}

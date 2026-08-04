"""GPU discovery, validation, and selection routes (goals.md sections 3-4).

- `GET /gpu-discovery` -- run discovery directly on the machine hosting the
  Farm Manager, since goals.md requires the Farm Manager to "manage the
  local machine as a worker too".
- `POST /gpu-discovery/validate` -- validate GPU records a *remote* worker
  self-reported at registration time (the coordinator can't shell out to
  `nvidia-smi` on a machine it isn't running on, so remote workers detect
  their own GPUs and the server independently re-checks them against the
  farm's join requirements).
- `GET`/`PUT /gpu-discovery/{worker_id}/selection` -- view/persist which of
  a worker's validated GPUs actually join the farm (individual, multiple,
  or all), surviving restarts.
- `POST /gpu-discovery/local/register` -- (re-)register the Farm Manager's
  own machine as a worker using only its currently selected, validated GPUs.
"""

from __future__ import annotations

from typing import Any

from engine.contracts import RegisterWorkerRequest, WorkerCapabilities
from engine.contracts.jobs import BackendKind
from fastapi import APIRouter, Body, Depends, HTTPException

from app.gpu_discovery import discover_and_validate, gpu_info_from_jsonable, validate_gpu
from app.gpu_selection import (
    GpuSelectionStore,
    annotate_with_selection,
    get_gpu_selection_store,
    gpu_identifier,
    selected_gpus,
)
from app.job_manager import get_job_manager

router = APIRouter(prefix="/gpu-discovery", tags=["gpu-discovery"])

#: Worker id the Farm Manager uses to represent its own host as a worker
#: (goals.md: "Manage the local machine as a worker too").
LOCAL_WORKER_ID = "local"


@router.get("")
def discover_local_gpus() -> dict[str, Any]:
    """Detect and validate GPUs on the Farm Manager's own machine."""

    results = discover_and_validate()
    return {"gpus": [result.to_jsonable() for result in results]}


@router.post("/validate")
def validate_reported_gpus(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Validate GPU records reported by a remote worker.

    Args:
        payload: `{"gpus": [<GpuInfo.to_jsonable() shaped dict>, ...]}`.

    Returns:
        Validation result per submitted GPU record.
    """

    reported = payload.get("gpus") or []
    results = [validate_gpu(gpu_info_from_jsonable(entry)).to_jsonable() for entry in reported]
    return {"gpus": results}


def _discover_and_validate_for_worker(worker_id: str, manager) -> list:
    """Return validation results for a worker's GPUs.

    For the local Farm Manager host, runs live discovery. For any other
    worker, the coordinator can't shell out to that machine's `nvidia-smi`
    -- instead it re-validates whatever GPU records that worker last
    self-reported at registration (see `app/routers/workers.py`).

    Args:
        worker_id: Worker identifier.
        manager: Job manager providing the last-known worker state.

    Returns:
        Validation results.

    Raises:
        HTTPException: 404 if `worker_id` is unknown and not the local host.
    """

    if worker_id == LOCAL_WORKER_ID:
        return discover_and_validate()

    worker = next((w for w in manager.list_workers() if w.worker_id == worker_id), None)
    if worker is None:
        raise HTTPException(status_code=404, detail=f"Unknown worker: {worker_id}")
    reported_gpus = (worker.capabilities.get("extra") or {}).get("gpus") or []
    return [validate_gpu(gpu_info_from_jsonable(entry)) for entry in reported_gpus]


@router.get("/{worker_id}/selection")
def get_gpu_selection(
    worker_id: str,
    manager=Depends(get_job_manager),
    store: GpuSelectionStore = Depends(get_gpu_selection_store),
) -> dict[str, Any]:
    """Return a worker's GPUs annotated with current selection state.

    Selection defaults to "all validated GPUs" until the operator saves an
    explicit choice (goals.md: individual / multiple / all GPUs).
    """

    validations = _discover_and_validate_for_worker(worker_id, manager)
    return {"worker_id": worker_id, "gpus": annotate_with_selection(worker_id, validations, store)}


@router.put("/{worker_id}/selection")
def set_gpu_selection(
    worker_id: str,
    payload: dict[str, Any] = Body(...),
    manager=Depends(get_job_manager),
    store: GpuSelectionStore = Depends(get_gpu_selection_store),
) -> dict[str, Any]:
    """Persist which of a worker's validated GPUs should join the farm.

    Args:
        worker_id: Worker identifier.
        payload: `{"selected": [<gpu identifier>, ...]}` -- identifiers as
            returned by `GET /gpu-discovery/{worker_id}/selection`.

    Returns:
        The updated selection view (same shape as the GET route).

    Raises:
        HTTPException: 400 if an identifier does not match any *validated*
            GPU currently known for this worker -- goals.md requires only
            validated GPUs to participate, so an invalid GPU cannot be
            force-selected.
    """

    validations = _discover_and_validate_for_worker(worker_id, manager)
    valid_identifiers = {gpu_identifier(v.gpu) for v in validations if v.valid}
    requested = list(payload.get("selected") or [])
    unknown = [identifier for identifier in requested if identifier not in valid_identifiers]
    if unknown:
        raise HTTPException(
            status_code=400,
            detail=f"Not a validated GPU for worker '{worker_id}': {', '.join(unknown)}",
        )
    store.set_selection(worker_id, requested)
    return {"worker_id": worker_id, "gpus": annotate_with_selection(worker_id, validations, store)}


@router.post("/local/register")
def register_local_worker(
    manager=Depends(get_job_manager),
    store: GpuSelectionStore = Depends(get_gpu_selection_store),
) -> dict[str, Any]:
    """(Re-)register the Farm Manager's own machine as a worker.

    Re-runs discovery, keeps only the GPUs that are both validated and
    currently selected (goals.md section 4: "Only selected GPUs become
    part of the farm"), and registers/updates the `local` worker with that
    filtered set -- realizing "manage the local machine as a worker too"
    (goals.md section 1) together with GPU selection.
    """

    validations = discover_and_validate()
    chosen = selected_gpus(LOCAL_WORKER_ID, validations, store)
    total_vram_gb = sum(gpu.vram_total_gb or 0.0 for gpu in chosen) or None
    capabilities = WorkerCapabilities(
        gpu_names=[gpu.name for gpu in chosen],
        total_vram_gb=total_vram_gb,
        supports_cuda=any(gpu.cuda_supported for gpu in chosen),
        extra={"gpus": [gpu.to_jsonable() for gpu in chosen]},
    )
    request = RegisterWorkerRequest(
        worker_id=LOCAL_WORKER_ID,
        backend=BackendKind.LOCAL,
        device="cuda" if chosen else "cpu",
        capabilities=capabilities,
    )
    response = manager.register_remote_worker(request)
    return {
        "registration": response.to_jsonable(),
        "selected_gpu_count": len(chosen),
        "gpus": annotate_with_selection(LOCAL_WORKER_ID, validations, store),
    }

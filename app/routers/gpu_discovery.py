"""GPU discovery & validation routes (goals.md sections 3-4).

Two use cases:

- `GET /gpu-discovery` -- run discovery directly on the machine hosting the
  Farm Manager, since goals.md requires the Farm Manager to "manage the
  local machine as a worker too".
- `POST /gpu-discovery/validate` -- validate GPU records a *remote* worker
  self-reported at registration time (the coordinator can't shell out to
  `nvidia-smi` on a machine it isn't running on, so remote workers detect
  their own GPUs and the server independently re-checks them against the
  farm's join requirements).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body

from app.gpu_discovery import GpuInfo, discover_and_validate, validate_gpu

router = APIRouter(prefix="/gpu-discovery", tags=["gpu-discovery"])


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
    results = []
    for entry in reported:
        gpu = GpuInfo(
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
        results.append(validate_gpu(gpu).to_jsonable())
    return {"gpus": results}

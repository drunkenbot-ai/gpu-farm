"""Farm-wide GPU inventory (goals.md sections 7-8: Resource Pools & Tagging).

A single place that assembles "every GPU currently joined to the farm" by
reading each registered worker's last-reported GPU list
(`capabilities.extra.gpus`, populated by GPU discovery/validation/selection
-- see `app/gpu_discovery.py`, `app/gpu_selection.py`, and the `/register`
and `/gpu-discovery/local/register` routes). Resource Pools and the tagging
system both operate on this inventory rather than talking to hardware
directly, since pools must be able to describe GPUs on workers that are not
the Farm Manager's own host.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.gpu_discovery import GpuInfo, gpu_info_from_jsonable
from app.gpu_selection import gpu_identifier
from app.tagging import TagStore, auto_tags_for_gpu, gpu_scope, worker_scope


@dataclass
class GpuInventoryEntry:
    """One GPU joined to the farm, with its worker context and tags.

    Attributes:
        worker_id: Owning worker's identifier.
        worker_backend: Owning worker's backend kind (e.g. "local").
        worker_status: Owning worker's availability ("available"/"busy"/"offline").
        worker_hostname: Owning worker's hostname, if reported.
        identifier: Stable GPU identifier (see `gpu_selection.gpu_identifier`).
        gpu: The GPU's hardware details.
        tags: Combined auto-derived and manually-assigned tags (deduplicated).
    """

    worker_id: str
    worker_backend: str
    worker_status: str
    worker_hostname: str | None
    identifier: str
    gpu: GpuInfo
    tags: list[str] = field(default_factory=list)

    def to_jsonable(self) -> dict[str, Any]:
        """Convert this entry to a JSON-friendly dict.

        Returns:
            Serializable dictionary.
        """

        return {
            "worker_id": self.worker_id,
            "worker_backend": self.worker_backend,
            "worker_status": self.worker_status,
            "worker_hostname": self.worker_hostname,
            "identifier": self.identifier,
            "gpu": self.gpu.to_jsonable(),
            "tags": self.tags,
        }


def build_inventory(manager, tag_store: TagStore) -> list[GpuInventoryEntry]:
    """Assemble the full farm-wide GPU inventory from registered workers.

    Args:
        manager: Job manager providing `list_workers()`.
        tag_store: Tag store providing manually-assigned tags.

    Returns:
        One `GpuInventoryEntry` per GPU currently joined to the farm (i.e.
        present in a registered worker's `capabilities.extra.gpus`).
    """

    entries: list[GpuInventoryEntry] = []
    for worker in manager.list_workers():
        reported_gpus = (worker.capabilities.get("extra") or {}).get("gpus") or []
        worker_manual_tags = tag_store.get_tags(worker_scope(worker.worker_id))
        for raw in reported_gpus:
            gpu = gpu_info_from_jsonable(raw)
            identifier = gpu_identifier(gpu)
            manual_tags = tag_store.get_tags(gpu_scope(worker.worker_id, identifier))
            tags = list(dict.fromkeys([*auto_tags_for_gpu(gpu), *worker_manual_tags, *manual_tags]))
            entries.append(
                GpuInventoryEntry(
                    worker_id=worker.worker_id,
                    worker_backend=worker.backend.value if hasattr(worker.backend, "value") else str(worker.backend),
                    worker_status=worker.status.value if hasattr(worker.status, "value") else str(worker.status),
                    worker_hostname=worker.hostname,
                    identifier=identifier,
                    gpu=gpu,
                    tags=tags,
                )
            )
    return entries

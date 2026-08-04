"""Training job scheduler (goals.md section 6).

Job assignment itself is still the `engine` submodule's pull-based
`handle_claim_job()` (a worker calls `/claim-job` and the coordinator hands
it the first compatible queued job by backend, `min_vram_gb`, and
`preferred_worker_id`/`tags`). This module adds the scheduling
considerations goals.md lists that the engine's matcher does not evaluate
on its own:

* GPU utilization / free VRAM (beyond the static `min_vram_gb` floor)
* CPU utilization
* RAM availability
* Disk space
* Resource pool selection
* Local mode vs cloud mode, and subscription/license validity for cloud

It is used two ways:

1. At job submission (`POST /jobs`) to resolve a Resource Pool down to a
   `preferred_worker_id` when the pool currently has exactly one eligible
   member, and to reject cloud jobs without a valid entitlement up front.
2. At claim time (`POST /claim-job`) to refuse to hand *any* job to a
   worker whose just-reported utilization/CPU/RAM/disk already exceed the
   configured thresholds -- preventing resource over-allocation onto a
   worker that is technically "available" but already saturated.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from app.config import Settings
from app.gpu_inventory import build_inventory
from app.pools import PoolStore, resolve_members
from app.tagging import TagStore


@dataclass
class SchedulingRequirements:
    """Requirements a candidate worker must satisfy to run a job.

    Attributes:
        backend: Backend kind the job needs to run on.
        min_vram_gb: Minimum total VRAM required, if any.
        resource_pool_id: Restrict candidates to this pool's current members.
        tags: Free-form tags the worker must carry (subset match, mirrors
            `engine`'s own `RuntimeSpec.tags` semantics).
    """

    backend: str = "local"
    min_vram_gb: Optional[float] = None
    resource_pool_id: Optional[str] = None
    tags: list[str] = field(default_factory=list)


@dataclass
class WorkerEligibility:
    """Result of evaluating one worker against scheduling requirements.

    Attributes:
        worker_id: Worker identifier.
        eligible: Whether the worker currently satisfies every check.
        reasons: Human-readable reasons for ineligibility (empty if eligible).
    """

    worker_id: str
    eligible: bool
    reasons: list[str] = field(default_factory=list)

    def to_jsonable(self) -> dict[str, Any]:
        """Convert to a JSON-friendly dict."""

        return {"worker_id": self.worker_id, "eligible": self.eligible, "reasons": self.reasons}


def resource_health(capabilities: dict[str, Any], settings: Settings) -> list[str]:
    """Check a worker's self-reported live resource state against thresholds.

    Reads optional live-utilization fields workers may report under
    `capabilities.extra` (`cpu_percent`, `ram_percent`, `disk_free_gb`) and
    per-GPU `utilization_percent` under `capabilities.extra.gpus`. Fields a
    worker doesn't report are treated as healthy (a worker that can't
    measure something shouldn't be starved of work because of it).

    Args:
        capabilities: A worker's `capabilities` dict (as stored on
            `WorkerDescriptor` or freshly submitted with a claim request).
        settings: Farm Manager settings providing the configured thresholds.

    Returns:
        Reasons the worker is currently over-saturated (empty if healthy).
    """

    reasons: list[str] = []
    extra = capabilities.get("extra") or {}

    cpu_percent = extra.get("cpu_percent")
    if cpu_percent is not None and cpu_percent > settings.scheduler_max_cpu_percent:
        reasons.append(f"CPU utilization {cpu_percent:.0f}% exceeds {settings.scheduler_max_cpu_percent:.0f}% limit.")

    ram_percent = extra.get("ram_percent")
    system_ram_gb = capabilities.get("system_ram_gb")
    if ram_percent is not None and system_ram_gb:
        free_ram_gb = system_ram_gb * (1 - ram_percent / 100.0)
        if free_ram_gb < settings.scheduler_min_free_ram_gb:
            reasons.append(f"Free RAM {free_ram_gb:.2f} GB is below the {settings.scheduler_min_free_ram_gb:.2f} GB minimum.")

    disk_free_gb = extra.get("disk_free_gb")
    if disk_free_gb is not None and disk_free_gb < settings.scheduler_min_free_disk_gb:
        reasons.append(f"Free disk {disk_free_gb:.2f} GB is below the {settings.scheduler_min_free_disk_gb:.2f} GB minimum.")

    gpu_utilizations = [
        gpu.get("utilization_percent")
        for gpu in (extra.get("gpus") or [])
        if gpu.get("utilization_percent") is not None
    ]
    if gpu_utilizations and max(gpu_utilizations) > settings.scheduler_max_gpu_utilization_percent:
        reasons.append(
            f"GPU utilization {max(gpu_utilizations):.0f}% exceeds "
            f"{settings.scheduler_max_gpu_utilization_percent:.0f}% limit."
        )

    return reasons


def _pool_member_worker_ids(
    resource_pool_id: Optional[str],
    manager,
    pool_store: PoolStore,
    tag_store: TagStore,
) -> Optional[set[str]]:
    """Resolve a pool id to the set of worker_ids currently in it.

    Returns:
        None if no pool restriction applies; otherwise the (possibly
        empty) set of member worker ids.
    """

    if not resource_pool_id:
        return None
    pool = pool_store.get_pool(resource_pool_id)
    if pool is None:
        return set()
    inventory = build_inventory(manager, tag_store)
    return {entry.worker_id for entry in resolve_members(pool, inventory)}


def evaluate_worker(
    worker,
    requirements: SchedulingRequirements,
    settings: Settings,
    pool_member_ids: Optional[set[str]],
) -> WorkerEligibility:
    """Evaluate whether one worker can currently take a job with these requirements.

    Args:
        worker: A `WorkerDescriptor` (or matching duck-typed object) from
            `manager.list_workers()`.
        requirements: Scheduling requirements for the job.
        settings: Farm Manager settings.
        pool_member_ids: Result of `_pool_member_worker_ids`, or None if no
            pool restriction applies.

    Returns:
        Eligibility verdict with human-readable reasons when ineligible.
    """

    reasons: list[str] = []
    status = worker.status.value if hasattr(worker.status, "value") else str(worker.status)
    backend = worker.backend.value if hasattr(worker.backend, "value") else str(worker.backend)

    if status != "available":
        reasons.append(f"Worker status is '{status}', not available.")
    if backend != requirements.backend:
        reasons.append(f"Worker backend '{backend}' does not match requested backend '{requirements.backend}'.")
    if requirements.min_vram_gb is not None:
        total_vram_gb = worker.capabilities.get("total_vram_gb")
        if not total_vram_gb or total_vram_gb < requirements.min_vram_gb:
            reasons.append(
                f"Worker VRAM {total_vram_gb or 0:.2f} GB is below the {requirements.min_vram_gb:.2f} GB requirement."
            )
    if requirements.tags:
        worker_labels = set(worker.capabilities.get("labels") or [])
        missing = set(requirements.tags) - worker_labels
        if missing:
            reasons.append(f"Worker is missing required tags: {', '.join(sorted(missing))}.")
    if pool_member_ids is not None and worker.worker_id not in pool_member_ids:
        reasons.append(f"Worker is not a member of resource pool '{requirements.resource_pool_id}'.")

    reasons.extend(resource_health(worker.capabilities, settings))
    return WorkerEligibility(worker_id=worker.worker_id, eligible=not reasons, reasons=reasons)


def local_system_resources() -> dict[str, Any]:
    """Sample this machine's live CPU/RAM/disk state via `psutil`.

    Returns:
        Dict with `hostname`, `cpu_count`, `system_ram_gb` (static specs, for
        `WorkerCapabilities`) plus `cpu_percent`, `ram_percent`,
        `disk_free_gb` (live utilization, for `WorkerCapabilities.extra` and
        `resource_health()`). Any field psutil can't provide is omitted
        rather than guessed.
    """

    import socket

    import psutil

    data: dict[str, Any] = {"hostname": socket.gethostname()}
    try:
        data["cpu_count"] = psutil.cpu_count(logical=True)
        data["cpu_percent"] = psutil.cpu_percent(interval=0.1)
    except Exception:
        pass
    try:
        vm = psutil.virtual_memory()
        data["system_ram_gb"] = round(vm.total / (1024**3), 2)
        data["ram_percent"] = vm.percent
    except Exception:
        pass
    try:
        disk = psutil.disk_usage(str_home_drive())
        data["disk_free_gb"] = round(disk.free / (1024**3), 2)
    except Exception:
        pass
    return data


def str_home_drive() -> str:
    """Return a filesystem path suitable for `psutil.disk_usage`.

    Uses the home directory's drive/mount so disk-space checks reflect the
    volume the Farm Manager actually writes artifacts/state to.
    """

    from pathlib import Path

    return str(Path.home().anchor or Path.home())


def evaluate_all_workers(
    requirements: SchedulingRequirements,
    manager,
    settings: Settings,
    pool_store: PoolStore,
    tag_store: TagStore,
) -> list[WorkerEligibility]:
    """Evaluate every known worker against a job's scheduling requirements.

    Args:
        requirements: Scheduling requirements for the job.
        manager: Job manager providing `list_workers()`.
        settings: Farm Manager settings.
        pool_store: Pool store used to resolve `requirements.resource_pool_id`.
        tag_store: Tag store used when resolving pool membership.

    Returns:
        One `WorkerEligibility` per known worker.
    """

    pool_member_ids = _pool_member_worker_ids(requirements.resource_pool_id, manager, pool_store, tag_store)
    return [evaluate_worker(w, requirements, settings, pool_member_ids) for w in manager.list_workers()]

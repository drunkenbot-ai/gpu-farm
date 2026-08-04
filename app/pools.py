"""Resource Pools (goals.md section 7).

A Resource Pool groups GPUs -- manually selected, matched by rule (vendor,
model, compute capability, VRAM size, driver version, machine, tags, ...),
or both -- so projects can target a pool instead of a specific GPU. Pools
are stored independently of any single worker so they can span the whole
farm.
"""

from __future__ import annotations

import json
import threading
import uuid
from dataclasses import asdict, dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

from app.gpu_inventory import GpuInventoryEntry

#: Rule fields resolvable against a `GpuInventoryEntry` (goals.md section 7
#: membership criteria). "cuda_major"/"cuda12" style grouping is expressed
#: via the `tags` field (auto-tags include a `cudaN` tag) rather than a
#: separate cuda-version rule field, since torch/driver CUDA version
#: reporting is not reliably available across all worker environments.
RULE_FIELDS = {"vendor", "model", "compute_capability", "vram_gb", "driver_version", "worker_id", "tags"}

#: Comparison operators supported by `matches_rule`.
RULE_OPS = {"eq", "contains", "gte", "lte", "in"}


def utc_now_iso() -> str:
    """Return the current UTC time as an ISO-8601 string."""

    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def member_key(worker_id: str, identifier: str) -> str:
    """Return the manual-membership key for a specific GPU.

    Args:
        worker_id: Owning worker's identifier.
        identifier: Stable GPU identifier (see `gpu_selection.gpu_identifier`).

    Returns:
        Composite key used in `ResourcePool.manual_members`.
    """

    return f"{worker_id}::{identifier}"


@dataclass
class PoolRule:
    """A single rule-based membership condition.

    Attributes:
        field: One of `RULE_FIELDS`.
        op: One of `RULE_OPS`.
        value: Comparison value (a list for `in`, a scalar otherwise).
    """

    field: str
    op: str
    value: Any

    def to_jsonable(self) -> dict[str, Any]:
        """Convert to a JSON-friendly dict."""

        return {"field": self.field, "op": self.op, "value": self.value}

    @classmethod
    def from_jsonable(cls, data: dict[str, Any]) -> "PoolRule":
        """Rebuild a rule from a `to_jsonable()`-shaped dict."""

        return cls(field=str(data["field"]), op=str(data["op"]), value=data.get("value"))


@dataclass
class ResourcePool:
    """A logical grouping of GPUs (goals.md section 7).

    Attributes:
        id: Stable pool identifier.
        name: Display name (e.g. "RTX 4090 Pool").
        description: Optional free-form description.
        enabled: Whether the pool is active for scheduling.
        manual_members: Explicitly added GPUs (`member_key()` values).
        rules: Rule-based membership conditions (all must match, AND'd).
        assigned_projects: Projects this pool is reserved for.
        created_at: ISO-8601 creation timestamp.
        updated_at: ISO-8601 last-update timestamp.
    """

    id: str
    name: str
    description: str = ""
    enabled: bool = True
    manual_members: list[str] = field(default_factory=list)
    rules: list[PoolRule] = field(default_factory=list)
    assigned_projects: list[str] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""

    def to_jsonable(self) -> dict[str, Any]:
        """Convert to a JSON-friendly dict."""

        data = asdict(self)
        data["rules"] = [rule.to_jsonable() for rule in self.rules]
        return data

    @classmethod
    def from_jsonable(cls, data: dict[str, Any]) -> "ResourcePool":
        """Rebuild a pool from a `to_jsonable()`-shaped dict."""

        rules = [PoolRule.from_jsonable(r) for r in data.get("rules") or []]
        return cls(
            id=data["id"],
            name=data["name"],
            description=data.get("description", ""),
            enabled=data.get("enabled", True),
            manual_members=list(data.get("manual_members") or []),
            rules=rules,
            assigned_projects=list(data.get("assigned_projects") or []),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
        )


def matches_rule(entry: GpuInventoryEntry, rule: PoolRule) -> bool:
    """Return whether an inventory entry satisfies one rule.

    Args:
        entry: Candidate GPU inventory entry.
        rule: Rule to evaluate.

    Returns:
        True if `entry` matches `rule`.
    """

    field_values = {
        "vendor": entry.gpu.vendor,
        "model": entry.gpu.name,
        "compute_capability": entry.gpu.compute_capability,
        "vram_gb": entry.gpu.vram_total_gb,
        "driver_version": entry.gpu.driver_version,
        "worker_id": entry.worker_id,
        "tags": entry.tags,
    }
    actual = field_values.get(rule.field)
    if actual is None:
        return False

    if rule.op == "eq":
        return str(actual).lower() == str(rule.value).lower()
    if rule.op == "contains":
        if isinstance(actual, list):
            return str(rule.value).lower() in [str(item).lower() for item in actual]
        return str(rule.value).lower() in str(actual).lower()
    if rule.op == "gte":
        return float(actual) >= float(rule.value)
    if rule.op == "lte":
        return float(actual) <= float(rule.value)
    if rule.op == "in":
        values = rule.value if isinstance(rule.value, list) else [rule.value]
        return str(actual).lower() in [str(v).lower() for v in values]
    return False


def resolve_members(pool: ResourcePool, inventory: list[GpuInventoryEntry]) -> list[GpuInventoryEntry]:
    """Resolve which inventory GPUs currently belong to a pool.

    Membership is the union of explicitly added GPUs and any GPU matching
    *every* rule (rules are AND'd; a GPU may belong to multiple pools
    simultaneously since this is just a filter, not an exclusive assignment).

    Args:
        pool: Pool to resolve.
        inventory: Full farm GPU inventory.

    Returns:
        Matching inventory entries, in inventory order, de-duplicated.
    """

    manual_keys = set(pool.manual_members)
    matched: list[GpuInventoryEntry] = []
    seen: set[str] = set()
    for entry in inventory:
        key = member_key(entry.worker_id, entry.identifier)
        is_manual = key in manual_keys
        is_rule_match = bool(pool.rules) and all(matches_rule(entry, rule) for rule in pool.rules)
        if (is_manual or is_rule_match) and key not in seen:
            matched.append(entry)
            seen.add(key)
    return matched


def pool_stats(members: list[GpuInventoryEntry], pool: ResourcePool) -> dict[str, Any]:
    """Compute the display stats goals.md requires for each pool.

    Args:
        members: Resolved pool members.
        pool: The pool itself (for `assigned_projects`).

    Returns:
        Dict with GPU count, available/busy counts, total VRAM, average
        utilization, and assigned projects.
    """

    total_vram = sum(m.gpu.vram_total_gb or 0.0 for m in members)
    utilizations = [m.gpu.utilization_percent for m in members if m.gpu.utilization_percent is not None]
    return {
        "gpu_count": len(members),
        "available_gpus": sum(1 for m in members if m.worker_status == "available"),
        "busy_gpus": sum(1 for m in members if m.worker_status == "busy"),
        "offline_gpus": sum(1 for m in members if m.worker_status == "offline"),
        "total_vram_gb": round(total_vram, 2) if members else 0.0,
        "average_utilization_percent": round(sum(utilizations) / len(utilizations), 2) if utilizations else None,
        "assigned_projects": pool.assigned_projects,
    }


def default_pool_store_path() -> Path:
    """Return the default on-disk path for persisted resource pools."""

    return Path.home() / ".drunkenbot_ide" / "gpu_farm" / "pools.json"


class PoolStore:
    """Persists Resource Pool definitions (membership resolved on read)."""

    def __init__(self, path: Optional[Path] = None) -> None:
        """Create a pool store backed by a JSON file.

        Args:
            path: Optional override path, mainly for tests.
        """

        self.path = Path(path) if path else default_pool_store_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def list_pools(self) -> list[ResourcePool]:
        """Return every defined pool."""

        return [ResourcePool.from_jsonable(p) for p in self._read().values()]

    def get_pool(self, pool_id: str) -> Optional[ResourcePool]:
        """Return one pool by id, or None if it doesn't exist."""

        data = self._read().get(pool_id)
        return ResourcePool.from_jsonable(data) if data else None

    def create_pool(
        self,
        name: str,
        description: str = "",
        rules: Optional[list[PoolRule]] = None,
        manual_members: Optional[list[str]] = None,
        assigned_projects: Optional[list[str]] = None,
    ) -> ResourcePool:
        """Create and persist a new pool.

        Args:
            name: Display name.
            description: Optional description.
            rules: Rule-based membership conditions.
            manual_members: Explicitly added GPUs (`member_key()` values).
            assigned_projects: Projects to reserve this pool for.

        Returns:
            The newly created pool.
        """

        now = utc_now_iso()
        pool = ResourcePool(
            id=uuid.uuid4().hex[:12],
            name=name,
            description=description,
            rules=rules or [],
            manual_members=manual_members or [],
            assigned_projects=assigned_projects or [],
            created_at=now,
            updated_at=now,
        )
        with self._lock:
            data = self._read()
            data[pool.id] = pool.to_jsonable()
            self._write(data)
        return pool

    def update_pool(self, pool_id: str, **changes: Any) -> Optional[ResourcePool]:
        """Apply partial updates to a pool (create/edit/rename/enable/disable).

        Args:
            pool_id: Pool identifier.
            **changes: Any subset of `ResourcePool` fields to overwrite
                (e.g. `name=`, `enabled=`, `rules=`, `manual_members=`,
                `assigned_projects=`, `description=`). `rules` may be
                passed as a list of `PoolRule` or of jsonable dicts.

        Returns:
            The updated pool, or None if `pool_id` doesn't exist.
        """

        with self._lock:
            data = self._read()
            existing = data.get(pool_id)
            if existing is None:
                return None
            pool = ResourcePool.from_jsonable(existing)
            for key, value in changes.items():
                if value is None:
                    continue
                if key == "rules":
                    value = [r if isinstance(r, PoolRule) else PoolRule.from_jsonable(r) for r in value]
                setattr(pool, key, value)
            pool.updated_at = utc_now_iso()
            data[pool_id] = pool.to_jsonable()
            self._write(data)
            return pool

    def delete_pool(self, pool_id: str) -> bool:
        """Delete a pool.

        Args:
            pool_id: Pool identifier.

        Returns:
            True if a pool was deleted, False if it didn't exist.
        """

        with self._lock:
            data = self._read()
            if pool_id not in data:
                return False
            del data[pool_id]
            self._write(data)
            return True

    def add_manual_member(self, pool_id: str, worker_id: str, identifier: str) -> Optional[ResourcePool]:
        """Add one GPU to a pool's manual membership list."""

        pool = self.get_pool(pool_id)
        if pool is None:
            return None
        key = member_key(worker_id, identifier)
        members = list(dict.fromkeys([*pool.manual_members, key]))
        return self.update_pool(pool_id, manual_members=members)

    def remove_manual_member(self, pool_id: str, worker_id: str, identifier: str) -> Optional[ResourcePool]:
        """Remove one GPU from a pool's manual membership list."""

        pool = self.get_pool(pool_id)
        if pool is None:
            return None
        key = member_key(worker_id, identifier)
        members = [m for m in pool.manual_members if m != key]
        return self.update_pool(pool_id, manual_members=members)

    def _read(self) -> dict[str, dict[str, Any]]:
        """Load the pool file, tolerating a missing/corrupt file."""

        if not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}

    def _write(self, data: dict[str, dict[str, Any]]) -> None:
        """Persist the full pool mapping to disk."""

        self.path.write_text(json.dumps(data, indent=2), encoding="utf-8")


@lru_cache
def get_pool_store() -> PoolStore:
    """Return the process-wide pool store singleton."""

    return PoolStore()

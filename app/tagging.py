"""Metadata tagging for workers and GPUs (goals.md section 8: "Tagging System").

Tags are free-form strings usable for Resource Pool membership, scheduling,
filtering, and search. Two kinds of tags exist for a GPU:

- **Auto tags** -- derived from detected hardware (vendor, model, CUDA major
  version, VRAM size bucket) so pools like "RTX 4090 Pool" or "CUDA 12 Pool"
  work out of the box with zero manual tagging.
- **Manual tags** -- operator-assigned, persisted per scope (a worker as a
  whole, or one specific GPU on a worker) so choices like "office",
  "experimental", or "project-alpha" survive restarts.
"""

from __future__ import annotations

import json
import re
import threading
from functools import lru_cache
from pathlib import Path
from typing import Optional

from app.gpu_discovery import GpuInfo


def default_tag_store_path() -> Path:
    """Return the default on-disk path for persisted manual tags."""

    return Path.home() / ".drunkenbot_ide" / "gpu_farm" / "tags.json"


def worker_scope(worker_id: str) -> str:
    """Return the tag-store scope key for a whole worker."""

    return f"worker:{worker_id}"


def gpu_scope(worker_id: str, identifier: str) -> str:
    """Return the tag-store scope key for a single GPU on a worker."""

    return f"gpu:{worker_id}:{identifier}"


def _slugify(value: str) -> str:
    """Lowercase and collapse a label into a tag-friendly slug."""

    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug


def auto_tags_for_gpu(gpu: GpuInfo) -> list[str]:
    """Derive automatic tags from a GPU's detected hardware.

    Args:
        gpu: Detected GPU.

    Returns:
        Auto-derived tags, e.g. `["nvidia", "geforce-gtx-1650", "cuda7",
        "4gb"]`. These always reflect current hardware and are never
        persisted -- they're recomputed on every read so they can't drift
        from reality.
    """

    tags: list[str] = []
    if gpu.vendor:
        tags.append(_slugify(gpu.vendor))
    if gpu.name:
        tags.append(_slugify(gpu.name))
    if gpu.compute_capability:
        major = str(gpu.compute_capability).split(".")[0]
        if major.isdigit():
            tags.append(f"cuda{major}")
    if gpu.vram_total_gb is not None:
        tags.append(f"{int(round(gpu.vram_total_gb))}gb")
    return [tag for tag in dict.fromkeys(tags) if tag]


class TagStore:
    """Persists operator-assigned tags per worker or per GPU scope."""

    def __init__(self, path: Optional[Path] = None) -> None:
        """Create a tag store backed by a JSON file.

        Args:
            path: Optional override path, mainly for tests.
        """

        self.path = Path(path) if path else default_tag_store_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def get_tags(self, scope: str) -> list[str]:
        """Return the manually-assigned tags for a scope.

        Args:
            scope: A key from `worker_scope()` or `gpu_scope()`.

        Returns:
            Persisted tags for that scope (empty list if none saved).
        """

        return list(self._read().get(scope, []))

    def set_tags(self, scope: str, tags: list[str]) -> list[str]:
        """Persist the manual tags for a scope, replacing any prior value.

        Args:
            scope: A key from `worker_scope()` or `gpu_scope()`.
            tags: New tag list (deduplicated, order-preserving).

        Returns:
            The stored, de-duplicated, slugified tag list.
        """

        with self._lock:
            data = self._read()
            cleaned = [_slugify(tag) for tag in tags if _slugify(tag)]
            deduped = list(dict.fromkeys(cleaned))
            data[scope] = deduped
            self._write(data)
            return deduped

    def _read(self) -> dict[str, list[str]]:
        """Load the tag file, tolerating a missing/corrupt file."""

        if not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}

    def _write(self, data: dict[str, list[str]]) -> None:
        """Persist the full tag mapping to disk."""

        self.path.write_text(json.dumps(data, indent=2), encoding="utf-8")


@lru_cache
def get_tag_store() -> TagStore:
    """Return the process-wide tag store singleton."""

    return TagStore()

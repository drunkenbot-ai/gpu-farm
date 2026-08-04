"""GPU selection persistence (goals.md section 4: "GPU Selection").

Machines may have multiple GPUs. The operator chooses which *validated*
GPUs actually join the farm -- individual GPUs, multiple GPUs, or all of
them -- and that choice must survive restarts (goals.md: "Selections must
persist across restarts").

Selection is stored per worker_id in a small JSON file rather than only in
memory, so it outlives both Farm Manager restarts and (once the worker EXE
in Phase 10 consults this API) worker machine reboots.
"""

from __future__ import annotations

import json
import threading
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

from app.gpu_discovery import GpuInfo, GpuValidationResult


def default_selection_store_path() -> Path:
    """Return the default on-disk path for persisted GPU selections."""

    return Path.home() / ".drunkenbot_ide" / "gpu_farm" / "gpu_selection.json"


def gpu_identifier(gpu: GpuInfo) -> str:
    """Return a stable identifier for a GPU across restarts/reboots.

    Prefers the GPU's UUID (stable across reboots and PCI slot changes),
    then its PCI bus id, and only falls back to its enumeration index --
    index alone is not stable if a machine's GPU order changes after a
    driver update or a card is added/removed.

    Args:
        gpu: Detected GPU.

    Returns:
        Stable string identifier suitable for persisted selections.
    """

    if gpu.uuid:
        return gpu.uuid
    if gpu.pci_id:
        return f"pci:{gpu.pci_id}"
    return f"idx:{gpu.index}"


class GpuSelectionStore:
    """Persists which GPUs are selected to join the farm, per worker."""

    def __init__(self, path: Optional[Path] = None) -> None:
        """Create a selection store backed by a JSON file.

        Args:
            path: Optional override path, mainly for tests.
        """

        self.path = Path(path) if path else default_selection_store_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def get_selection(self, worker_id: str) -> Optional[list[str]]:
        """Return the persisted GPU selection for a worker.

        Args:
            worker_id: Worker identifier.

        Returns:
            Saved list of selected GPU identifiers, or None if this worker
            has never saved an explicit selection -- callers should treat
            None as "all currently-validated GPUs selected by default" so
            a freshly joined machine is immediately usable.
        """

        value = self._read().get(worker_id)
        return list(value) if value is not None else None

    def set_selection(self, worker_id: str, identifiers: list[str]) -> list[str]:
        """Persist a worker's GPU selection.

        Args:
            worker_id: Worker identifier.
            identifiers: Selected GPU identifiers (see `gpu_identifier`).

        Returns:
            The stored, de-duplicated identifier list.
        """

        with self._lock:
            data = self._read()
            deduped = list(dict.fromkeys(identifiers))
            data[worker_id] = deduped
            self._write(data)
            return deduped

    def _read(self) -> dict[str, list[str]]:
        """Load the selection file, tolerating a missing/corrupt file."""

        if not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}

    def _write(self, data: dict[str, list[str]]) -> None:
        """Persist the full selection mapping to disk."""

        self.path.write_text(json.dumps(data, indent=2), encoding="utf-8")


@lru_cache
def get_gpu_selection_store() -> GpuSelectionStore:
    """Return the process-wide GPU selection store singleton."""

    return GpuSelectionStore()


def annotate_with_selection(
    worker_id: str,
    validations: list[GpuValidationResult],
    store: GpuSelectionStore,
) -> list[dict[str, Any]]:
    """Annotate each validated GPU with its stable identifier and selection state.

    Args:
        worker_id: Worker identifier whose selection to apply.
        validations: Validation results for every GPU detected on the worker.
        store: Selection store to read from.

    Returns:
        One dict per GPU: its validation payload plus `identifier` and
        `selected`. Invalid GPUs are never treated as selected, even if a
        stale selection references them.
    """

    selected_ids = store.get_selection(worker_id)
    annotated: list[dict[str, Any]] = []
    for validation in validations:
        identifier = gpu_identifier(validation.gpu)
        if not validation.valid:
            is_selected = False
        elif selected_ids is None:
            is_selected = True  # No explicit selection yet: default to "all validated GPUs".
        else:
            is_selected = identifier in selected_ids
        entry = validation.to_jsonable()
        entry["identifier"] = identifier
        entry["selected"] = is_selected
        annotated.append(entry)
    return annotated


def selected_gpus(
    worker_id: str,
    validations: list[GpuValidationResult],
    store: GpuSelectionStore,
) -> list[GpuInfo]:
    """Return only the GPUs that are both validated and currently selected.

    Args:
        worker_id: Worker identifier whose selection to apply.
        validations: Validation results for every GPU detected on the worker.
        store: Selection store to read from.

    Returns:
        Selected, validated GPUs -- the set that should actually join the
        farm as trainable resources for this worker.
    """

    annotated = annotate_with_selection(worker_id, validations, store)
    valid_by_identifier = {gpu_identifier(v.gpu): v.gpu for v in validations if v.valid}
    return [
        valid_by_identifier[entry["identifier"]]
        for entry in annotated
        if entry["selected"] and entry["identifier"] in valid_by_identifier
    ]

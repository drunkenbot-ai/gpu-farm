"""Shared `JobManager` instance for the Farm Manager process.

The engine's `JobManager` (from the `engine` git submodule) already owns
worker/job state and JSON-file persistence (`engine.coordinator.state_store`).
The Farm Manager backend wraps it rather than re-implementing job
orchestration -- see plan phase 1.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from engine.coordinator.job_manager import JobManager

from app.config import get_settings


@lru_cache
def get_job_manager() -> JobManager:
    """Return the process-wide job manager singleton.

    Returns:
        Shared `JobManager` instance backing all Farm Manager routes.
    """

    settings = get_settings()
    Path(settings.artifact_root).mkdir(parents=True, exist_ok=True)
    return JobManager()

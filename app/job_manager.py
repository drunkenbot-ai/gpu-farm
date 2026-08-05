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
from engine.coordinator.state_store import JobStateStore

from app.config import get_settings


@lru_cache
def get_job_manager() -> JobManager:
    """Return the process-wide job manager singleton.

    Returns:
        Shared `JobManager` instance backing all Farm Manager routes.
    """

    settings = get_settings()
    artifact_root = Path(settings.artifact_root)
    artifact_root.mkdir(parents=True, exist_ok=True)
    # Do not inherit the engine's user-home default: a server/service account
    # may not have a writable profile, and farm state must stay with the farm.
    database = settings.database_url.removeprefix("sqlite:///")
    state_path = Path(database).with_name("coordinator_state.sqlite3")
    return JobManager(state_store=JobStateStore(state_path))

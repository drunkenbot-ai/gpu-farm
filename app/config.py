"""Farm Manager configuration.

Settings are environment-driven (see `.env.example`) so the same backend
image can run in either workflow without code changes:

- ``FARM_MODE=local`` -- private farm, never contacts cloud-service.
- ``FARM_MODE=cloud`` -- shared farm, gates access on cloud-service
  entitlement (``CLOUD_SERVICE_URL`` + a per-request API key).
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Farm Manager runtime settings."""

    model_config = SettingsConfigDict(env_file=".env", env_prefix="", extra="ignore")

    farm_mode: Literal["local", "cloud"] = "local"
    host: str = "0.0.0.0"
    port: int = 8080

    database_url: str = "sqlite:///./farm_manager.db"

    # Artifact storage root for project/job file distribution (Phase 8).
    artifact_root: str = "./artifacts"

    # Only used when farm_mode == "cloud". Points at the drunkenbot-ai/cloud-service
    # deployment that owns /auth/validate-key entitlement checks.
    cloud_service_url: str = "https://cloud.drunkenbot.ai"
    cloud_service_timeout_seconds: float = 15.0

    stale_worker_timeout_seconds: int = 30


@lru_cache
def get_settings() -> Settings:
    """Return cached process-wide settings."""

    return Settings()

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
    cloud_usage_report_path: str = "/auth/report-usage"

    # Comma-separated browser origins. Keep explicit in deployments; the
    # dashboard served by this process does not require CORS at all.
    cors_origins: str = "http://localhost:8080,http://127.0.0.1:8080"
    farm_admin_token: str = ""

    stale_worker_timeout_seconds: int = 30

    # Scheduler resource-health thresholds (goals.md section 6): a worker
    # exceeding any of these is treated as unavailable for new work even if
    # it calls /claim-job, preventing over-allocation onto an already
    # saturated machine.
    scheduler_max_gpu_utilization_percent: float = 95.0
    scheduler_max_cpu_percent: float = 90.0
    scheduler_min_free_ram_gb: float = 1.0
    scheduler_min_free_disk_gb: float = 5.0

    @property
    def parsed_cors_origins(self) -> list[str]:
        """Return configured non-empty CORS origins."""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    """Return cached process-wide settings."""

    return Settings()

"""Cloud GPU Farm entitlement checks against `drunkenbot-ai/cloud-service`.

Only used when `FARM_MODE=cloud`. The Local GPU Farm workflow must never
import or call anything in this module (goals.md section 9/10).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import httpx

from app.config import Settings


@dataclass
class EntitlementResult:
    """Result of a cloud-service `/auth/validate-key` check."""

    valid: bool
    reason: str = ""
    tier: Optional[str] = None
    quota_gpu_hours_per_month: Optional[float] = None
    account_id: Optional[str] = None


async def validate_cloud_api_key(api_key: str, settings: Settings) -> EntitlementResult:
    """Validate a cloud GPU-hours API key against cloud-service.

    Args:
        api_key: Bearer API key presented by the caller (worker or dashboard
            user requesting cloud pool access).
        settings: Farm Manager settings (cloud-service URL/timeout).

    Returns:
        Entitlement result. Any network failure is treated as *not valid*
        -- cloud pool access must fail closed, unlike LLM-IDE's own license
        check which has an offline grace period. GPU-hours accounting has
        no equivalent "grace" concept in goals.md.
    """

    url = f"{settings.cloud_service_url.rstrip('/')}/auth/validate-key"
    try:
        async with httpx.AsyncClient(timeout=settings.cloud_service_timeout_seconds) as client:
            response = await client.post(url, headers={"Authorization": f"Bearer {api_key}"})
    except httpx.HTTPError as exc:
        return EntitlementResult(valid=False, reason=f"cloud-service unreachable: {exc}")

    if response.status_code != 200:
        return EntitlementResult(valid=False, reason=f"cloud-service returned HTTP {response.status_code}")

    payload = response.json()
    if not payload.get("valid"):
        return EntitlementResult(valid=False, reason=payload.get("reason", "API key not valid."))

    return EntitlementResult(
        valid=True,
        tier=payload.get("tier"),
        quota_gpu_hours_per_month=payload.get("quota_gpu_hours_per_month"),
        account_id=payload.get("account_id"),
    )


async def report_cloud_usage(api_key: str, usage: dict, settings: Settings) -> tuple[bool, str]:
    """Submit one completed job's measured GPU-hours to cloud-service."""
    url = f"{settings.cloud_service_url.rstrip('/')}{settings.cloud_usage_report_path}"
    try:
        async with httpx.AsyncClient(timeout=settings.cloud_service_timeout_seconds) as client:
            response = await client.post(url, headers={"Authorization": f"Bearer {api_key}"}, json=usage)
    except httpx.HTTPError as exc:
        return False, f"cloud-service unreachable: {exc}"
    if response.status_code != 200:
        return False, f"cloud-service returned HTTP {response.status_code}"
    payload = response.json()
    return bool(payload.get("accepted", payload.get("ok", True))), str(payload.get("reason", ""))

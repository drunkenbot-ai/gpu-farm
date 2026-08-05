from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException
from app.cloud_entitlement import report_cloud_usage, validate_cloud_api_key
from app.cloud_usage import mark_reported, pending, summary
from app.config import get_settings

router = APIRouter(prefix="/cloud", tags=["cloud"])

@router.get("/status")
async def cloud_status(authorization: str = Header(default="")) -> dict:
    settings = get_settings()
    if settings.farm_mode != "cloud":
        return {"enabled": False, "reason": "Farm Manager is in local mode."}
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing cloud GPU-hours API key.")
    entitlement = await validate_cloud_api_key(authorization.removeprefix("Bearer ").strip(), settings)
    if not entitlement.valid:
        raise HTTPException(403, entitlement.reason)
    usage = summary(entitlement.account_id)
    quota = entitlement.quota_gpu_hours_per_month
    return {"enabled": True, "tier": entitlement.tier, "account_id": entitlement.account_id,
        "quota_gpu_hours_per_month": quota, **usage,
        "gpu_hours_remaining": max(0.0, quota - usage["gpu_hours_consumed"]) if quota is not None else None,
        "reporting": "pending cloud-service usage-report endpoint"}


@router.post("/report-usage")
async def report_usage(authorization: str = Header(default="")) -> dict:
    """Replay completed, unreported jobs without storing API keys at rest."""
    settings = get_settings()
    if settings.farm_mode != "cloud":
        raise HTTPException(409, "Cloud reporting is unavailable in local mode.")
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing cloud GPU-hours API key.")
    api_key = authorization.removeprefix("Bearer ").strip()
    entitlement = await validate_cloud_api_key(api_key, settings)
    if not entitlement.valid or not entitlement.account_id:
        raise HTTPException(403, entitlement.reason or "Invalid cloud entitlement.")
    reported, failed = [], []
    for item in pending(entitlement.account_id):
        ok, reason = await report_cloud_usage(api_key, item, settings)
        if ok:
            mark_reported(item["job_id"], "reported"); reported.append(item["job_id"])
        else:
            # Keep it pending so a later operator retry is safe and does not
            # lose billable usage during a cloud-service outage.
            failed.append({"job_id": item["job_id"], "reason": reason})
    return {"reported": reported, "failed": failed}

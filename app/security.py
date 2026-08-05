"""Optional operator authentication for Farm Manager mutation endpoints."""
from __future__ import annotations

import secrets
from fastapi import Header, HTTPException
from app.config import get_settings


def require_operator(x_farm_admin_token: str = Header(default="")) -> None:
    """Require the configured operator token when one is enabled.

    Leaving ``FARM_ADMIN_TOKEN`` empty preserves trusted private-LAN setup.
    Production deployments must set a long random value and send it in the
    ``X-Farm-Admin-Token`` header for administrative mutations.
    """
    expected = get_settings().farm_admin_token
    if expected and not secrets.compare_digest(x_farm_admin_token, expected):
        raise HTTPException(status_code=401, detail="Missing or invalid Farm Manager operator token.")

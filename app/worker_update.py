"""Signed-release manifest checking for the packaged Windows worker."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path

import httpx

WORKER_VERSION = "0.1.0"


@dataclass(frozen=True)
class UpdateInfo:
    available: bool
    version: str = ""
    download_url: str = ""
    sha256: str = ""
    reason: str = ""


def check_for_update(manifest_url: str, current_version: str = WORKER_VERSION) -> UpdateInfo:
    """Fetch the public release manifest; never download or execute code."""
    if not manifest_url:
        return UpdateInfo(False, reason="No update manifest URL configured.")
    try:
        response = httpx.get(manifest_url, timeout=10.0)
        response.raise_for_status()
        data = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        return UpdateInfo(False, reason=f"Update check failed: {exc}")
    version = str(data.get("version", ""))
    url = str(data.get("installer_url", ""))
    digest = str(data.get("sha256", "")).lower()
    if not version or not url or len(digest) != 64:
        return UpdateInfo(False, reason="Invalid update manifest.")
    return UpdateInfo(_version_key(version) > _version_key(current_version), version, url, digest)


def verify_installer(path: Path, expected_sha256: str) -> bool:
    """Verify an operator-downloaded installer against its release manifest."""
    return hashlib.sha256(path.read_bytes()).hexdigest().lower() == expected_sha256.lower()


def _version_key(version: str) -> tuple[int, ...]:
    try:
        return tuple(int(part) for part in version.lstrip("v").split("."))
    except ValueError:
        return ()

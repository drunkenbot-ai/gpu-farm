"""Windows Credential Manager storage for worker cloud API keys."""
from __future__ import annotations

SERVICE = "DrunkenBotGPUFarm"


def credential_name(manager_url: str, mode: str) -> str:
    return f"{mode}:{manager_url.rstrip('/').lower()}"


def save_cloud_api_key(manager_url: str, api_key: str) -> None:
    import keyring
    keyring.set_password(SERVICE, credential_name(manager_url, "cloud"), api_key)


def load_cloud_api_key(manager_url: str) -> str | None:
    import keyring
    return keyring.get_password(SERVICE, credential_name(manager_url, "cloud"))


def delete_cloud_api_key(manager_url: str) -> None:
    import keyring
    try: keyring.delete_password(SERVICE, credential_name(manager_url, "cloud"))
    except keyring.errors.PasswordDeleteError: pass

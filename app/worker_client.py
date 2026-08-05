"""Entry point used by the Windows worker EXE and by local development."""
from __future__ import annotations
import argparse
from pathlib import Path
from engine.contracts import BackendKind
from engine.worker import WorkerClientConfig, run_worker_client
from app.worker_credentials import delete_cloud_api_key, load_cloud_api_key, save_cloud_api_key
from app.worker_update import WORKER_VERSION, check_for_update

def main() -> None:
    parser = argparse.ArgumentParser(description="GPU Farm Worker")
    parser.add_argument("--manager", required=True, help="Farm Manager base URL")
    parser.add_argument("--worker-id")
    parser.add_argument("--mode", choices=("local", "cloud"), default="local")
    parser.add_argument("--api-key", help="Cloud GPU-hours API key (cloud mode only)")
    parser.add_argument("--store-api-key", action="store_true", help="Store --api-key in Windows Credential Manager")
    parser.add_argument("--delete-stored-api-key", action="store_true")
    parser.add_argument("--workspace", default=str(Path.home() / ".drunkenbot_gpu_farm" / "workspace"))
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--version", action="version", version=f"GPUFarmWorker {WORKER_VERSION}")
    parser.add_argument("--update-manifest-url", default="", help="HTTPS URL of the signed worker release manifest")
    parser.add_argument("--check-update", action="store_true", help="Check the release manifest and exit")
    args = parser.parse_args()
    if args.check_update:
        result = check_for_update(args.update_manifest_url)
        if result.available:
            print(f"Update available: {result.version} {result.download_url} sha256={result.sha256}")
            return
        print(result.reason or "GPU Farm Worker is up to date.")
        return
    if args.delete_stored_api_key:
        delete_cloud_api_key(args.manager); return
    if args.store_api_key:
        if not args.api_key: parser.error("--store-api-key requires --api-key")
        save_cloud_api_key(args.manager, args.api_key)
    api_key = args.api_key or (load_cloud_api_key(args.manager) if args.mode == "cloud" else None)
    if args.mode == "cloud" and not api_key: parser.error("cloud mode requires --api-key or a stored credential")
    run_worker_client(WorkerClientConfig(coordinator_url=args.manager, worker_id=args.worker_id or WorkerClientConfig().worker_id,
        backend=BackendKind(args.mode), api_key=api_key, workspace_dir=Path(args.workspace), execute_jobs=True, claim_once=args.once))

if __name__ == "__main__": main()

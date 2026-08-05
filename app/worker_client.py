"""Entry point used by the Windows worker EXE and by local development."""
from __future__ import annotations
import argparse
from pathlib import Path
from engine.contracts import BackendKind
from engine.worker import WorkerClientConfig, run_worker_client

def main() -> None:
    parser = argparse.ArgumentParser(description="GPU Farm Worker")
    parser.add_argument("--manager", required=True, help="Farm Manager base URL")
    parser.add_argument("--worker-id")
    parser.add_argument("--mode", choices=("local", "cloud"), default="local")
    parser.add_argument("--api-key", help="Cloud GPU-hours API key (cloud mode only)")
    parser.add_argument("--workspace", default=str(Path.home() / ".drunkenbot_gpu_farm" / "workspace"))
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    run_worker_client(WorkerClientConfig(coordinator_url=args.manager, worker_id=args.worker_id or WorkerClientConfig().worker_id,
        backend=BackendKind(args.mode), api_key=args.api_key, workspace_dir=Path(args.workspace), execute_jobs=True, claim_once=args.once))

if __name__ == "__main__": main()

"""Windows system-tray host for the packaged worker client."""
from __future__ import annotations

import argparse
import os
import sys
import threading
from pathlib import Path

from engine.contracts import BackendKind
from engine.worker import WorkerClientConfig, run_worker_client


def _startup_value() -> str:
    executable = Path(sys.executable if getattr(sys, "frozen", False) else sys.argv[0]).resolve()
    return f'"{executable}" --manager http://127.0.0.1:8080'


def _set_autostart(enable: bool) -> None:
    if os.name != "nt":
        raise RuntimeError("Worker auto-start is only supported on Windows.")
    import winreg
    key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_SET_VALUE)
    try:
        if enable: winreg.SetValueEx(key, "GPUFarmWorker", 0, winreg.REG_SZ, _startup_value())
        else:
            try: winreg.DeleteValue(key, "GPUFarmWorker")
            except FileNotFoundError: pass
    finally: winreg.CloseKey(key)


def main() -> None:
    parser = argparse.ArgumentParser(description="GPU Farm Worker tray client")
    parser.add_argument("--manager", default="http://127.0.0.1:8080")
    parser.add_argument("--worker-id")
    parser.add_argument("--mode", choices=("local", "cloud"), default="local")
    parser.add_argument("--api-key", help="Cloud GPU-hours API key (cloud mode only)")
    parser.add_argument("--workspace", default=str(Path.home() / ".drunkenbot_gpu_farm" / "workspace"))
    parser.add_argument("--install-autostart", action="store_true")
    parser.add_argument("--remove-autostart", action="store_true")
    args = parser.parse_args()
    if args.install_autostart or args.remove_autostart:
        _set_autostart(args.install_autostart); return
    import pystray
    from PIL import Image
    stop = threading.Event()
    config = WorkerClientConfig(coordinator_url=args.manager, worker_id=args.worker_id or WorkerClientConfig().worker_id,
        backend=BackendKind(args.mode), api_key=args.api_key, workspace_dir=Path(args.workspace), execute_jobs=True)
    # The engine client cooperatively observes manager stop requests. The tray
    # action exits the host process after its current request completes.
    thread = threading.Thread(target=run_worker_client, args=(config,), daemon=True, name="gpu-farm-worker")
    thread.start()
    icon = pystray.Icon("GPUFarmWorker", Image.new("RGBA", (64, 64), "#1677ff"), "GPU Farm Worker")
    icon.menu = pystray.Menu(pystray.MenuItem("Quit", lambda: icon.stop()))
    icon.run()


if __name__ == "__main__": main()

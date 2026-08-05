"""Windows system-tray host for the packaged worker client."""
from __future__ import annotations

import argparse
import os
import sys
import threading
from pathlib import Path

from engine.contracts import BackendKind
from engine.worker import WorkerClientConfig, run_worker_client
from app.worker_credentials import delete_cloud_api_key, load_cloud_api_key, save_cloud_api_key
from app.worker_settings import load as load_settings, save as save_settings


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
    saved = load_settings()
    parser = argparse.ArgumentParser(description="GPU Farm Worker tray client")
    parser.add_argument("--manager", default=saved.get("manager", "http://127.0.0.1:8080"))
    parser.add_argument("--worker-id")
    parser.add_argument("--mode", choices=("local", "cloud"), default=saved.get("mode", "local"))
    parser.add_argument("--api-key", help="Cloud GPU-hours API key (cloud mode only)")
    parser.add_argument("--store-api-key", action="store_true")
    parser.add_argument("--delete-stored-api-key", action="store_true")
    parser.add_argument("--workspace", default=str(Path.home() / ".drunkenbot_gpu_farm" / "workspace"))
    parser.add_argument("--install-autostart", action="store_true")
    parser.add_argument("--remove-autostart", action="store_true")
    args = parser.parse_args()
    save_settings({"manager": args.manager, "mode": args.mode, "workspace": args.workspace})
    if args.delete_stored_api_key:
        delete_cloud_api_key(args.manager); return
    if args.store_api_key:
        if not args.api_key: parser.error("--store-api-key requires --api-key")
        save_cloud_api_key(args.manager, args.api_key)
    if args.install_autostart or args.remove_autostart:
        _set_autostart(args.install_autostart); return
    import pystray
    from PIL import Image
    stop = threading.Event()
    api_key = args.api_key or (load_cloud_api_key(args.manager) if args.mode == "cloud" else None)
    if args.mode == "cloud" and not api_key: parser.error("cloud mode requires --api-key or a stored credential")
    config = WorkerClientConfig(coordinator_url=args.manager, worker_id=args.worker_id or WorkerClientConfig().worker_id,
        backend=BackendKind(args.mode), api_key=api_key, workspace_dir=Path(args.workspace), execute_jobs=True)
    # The engine client cooperatively observes manager stop requests. The tray
    # action exits the host process after its current request completes.
    thread = threading.Thread(target=run_worker_client, args=(config,), daemon=True, name="gpu-farm-worker")
    thread.start()
    icon = pystray.Icon("GPUFarmWorker", Image.new("RGBA", (64, 64), "#1677ff"), "GPU Farm Worker")
    icon.menu = pystray.Menu(pystray.MenuItem("Open configuration", lambda: _configuration_dialog(args, icon)), pystray.MenuItem("Quit", lambda: icon.stop()))
    icon.run()


def _configuration_dialog(args, icon) -> None:
    """Small native dialog; changes are used on the next worker start."""
    import tkinter as tk
    root = tk.Tk(); root.title("GPU Farm Worker configuration")
    manager = tk.StringVar(value=args.manager); mode = tk.StringVar(value=args.mode)
    tk.Label(root, text="Farm Manager URL").pack(); tk.Entry(root, textvariable=manager, width=48).pack()
    tk.Label(root, text="Mode").pack(); tk.OptionMenu(root, mode, "local", "cloud").pack()
    def apply():
        save_settings({"manager": manager.get().strip(), "mode": mode.get(), "workspace": args.workspace})
        root.destroy(); icon.notify("GPU Farm Worker", "Configuration saved; restart the worker to apply it.")
    tk.Button(root, text="Save", command=apply).pack(); root.mainloop()


if __name__ == "__main__": main()

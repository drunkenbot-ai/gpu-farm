"""Per-user non-secret worker settings for the tray application."""
from __future__ import annotations
import json
from pathlib import Path

PATH = Path.home() / '.drunkenbot_gpu_farm' / 'worker_settings.json'

def load() -> dict:
    try: return json.loads(PATH.read_text(encoding='utf-8'))
    except (OSError, ValueError): return {}

def save(values: dict) -> None:
    PATH.parent.mkdir(parents=True, exist_ok=True)
    PATH.write_text(json.dumps(values, indent=2), encoding='utf-8')

"""Durable farm telemetry history, intentionally independent of run metrics."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import get_settings


def _connection() -> sqlite3.Connection:
    url = get_settings().database_url
    path = url.removeprefix("sqlite:///") if url.startswith("sqlite:///") else "farm_manager.db"
    connection = sqlite3.connect(path)
    connection.execute("""CREATE TABLE IF NOT EXISTS farm_telemetry (
        id INTEGER PRIMARY KEY, recorded_at TEXT NOT NULL, worker_id TEXT NOT NULL,
        kind TEXT NOT NULL, payload TEXT NOT NULL)""")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_farm_telemetry_worker_time ON farm_telemetry(worker_id, recorded_at)")
    return connection


def record(worker_id: str, kind: str, payload: dict[str, Any]) -> None:
    with _connection() as connection:
        connection.execute("INSERT INTO farm_telemetry(recorded_at,worker_id,kind,payload) VALUES (?,?,?,?)",
            (datetime.now(timezone.utc).isoformat(), worker_id, kind, json.dumps(payload)))


def history(worker_id: str | None = None, kind: str | None = None, limit: int = 500) -> list[dict[str, Any]]:
    limit = max(1, min(limit, 10_000))
    clauses, values = [], []
    if worker_id:
        clauses.append("worker_id=?"); values.append(worker_id)
    if kind:
        clauses.append("kind=?"); values.append(kind)
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    with _connection() as connection:
        rows = connection.execute(f"SELECT recorded_at,worker_id,kind,payload FROM farm_telemetry{where} ORDER BY id DESC LIMIT ?", [*values, limit]).fetchall()
    return [{"recorded_at": row[0], "worker_id": row[1], "kind": row[2], "payload": json.loads(row[3])} for row in reversed(rows)]

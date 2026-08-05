"""Durable operator audit trail for Farm Manager administrative actions."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from app.config import get_settings


def _connection() -> sqlite3.Connection:
    url = get_settings().database_url
    path = url.removeprefix("sqlite:///") if url.startswith("sqlite:///") else "farm_manager.db"
    connection = sqlite3.connect(path)
    connection.execute("""CREATE TABLE IF NOT EXISTS farm_audit_log (
        id INTEGER PRIMARY KEY, recorded_at TEXT NOT NULL, actor TEXT NOT NULL,
        action TEXT NOT NULL, path TEXT NOT NULL, status_code INTEGER NOT NULL,
        client_ip TEXT)""")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_farm_audit_time ON farm_audit_log(recorded_at)")
    return connection


def record(actor: str, action: str, path: str, status_code: int, client_ip: str | None) -> None:
    with _connection() as connection:
        connection.execute("INSERT INTO farm_audit_log(recorded_at,actor,action,path,status_code,client_ip) VALUES (?,?,?,?,?,?)", (datetime.now(timezone.utc).isoformat(), actor, action, path, status_code, client_ip))


def history(limit: int = 500) -> list[dict[str, object]]:
    with _connection() as connection:
        rows = connection.execute("SELECT recorded_at,actor,action,path,status_code,client_ip FROM farm_audit_log ORDER BY id DESC LIMIT ?", (max(1, min(limit, 10_000)),)).fetchall()
    return [{"recorded_at": row[0], "actor": row[1], "action": row[2], "path": row[3], "status_code": row[4], "client_ip": row[5]} for row in reversed(rows)]

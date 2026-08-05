"""Farm-side cloud GPU-hour ledger.

The cloud service remains the source of truth for billing.  This ledger gives
the manager immediate quota visibility and produces usage records ready for
the cloud-service reporting endpoint when it is enabled.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import get_settings


def _connection() -> sqlite3.Connection:
    settings = get_settings()
    database = settings.database_url.removeprefix("sqlite:///")
    connection = sqlite3.connect(database)
    connection.execute("""CREATE TABLE IF NOT EXISTS cloud_usage (
        job_id TEXT PRIMARY KEY, account_id TEXT NOT NULL, started_at TEXT,
        completed_at TEXT, gpu_count INTEGER NOT NULL DEFAULT 1,
        gpu_hours REAL NOT NULL DEFAULT 0, report_status TEXT NOT NULL DEFAULT 'pending')""")
    return connection


def start(job_id: str, account_id: str, gpu_count: int = 1) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with _connection() as connection:
        connection.execute("INSERT OR IGNORE INTO cloud_usage(job_id,account_id,started_at,gpu_count) VALUES (?,?,?,?)", (job_id, account_id, now, max(1, gpu_count)))


def complete(job_id: str) -> float:
    now = datetime.now(timezone.utc)
    with _connection() as connection:
        row = connection.execute("SELECT started_at,gpu_count FROM cloud_usage WHERE job_id=?", (job_id,)).fetchone()
        if not row:
            return 0.0
        started = datetime.fromisoformat(row[0]) if row[0] else now
        hours = max(0.0, (now - started).total_seconds() / 3600 * row[1])
        connection.execute("UPDATE cloud_usage SET completed_at=?,gpu_hours=?,report_status='pending' WHERE job_id=?", (now.isoformat(), hours, job_id))
    return hours


def summary(account_id: str | None = None) -> dict:
    clause, values = (" WHERE account_id=?", [account_id]) if account_id else ("", [])
    with _connection() as connection:
        hours, records = connection.execute(f"SELECT COALESCE(SUM(gpu_hours),0), COUNT(*) FROM cloud_usage{clause}", values).fetchone()
        pending = connection.execute(f"SELECT COUNT(*) FROM cloud_usage{clause}{' AND' if clause else ' WHERE'} report_status='pending'", values).fetchone()[0]
    return {"account_id": account_id, "gpu_hours_consumed": hours, "usage_records": records, "pending_reports": pending}


def pending(account_id: str) -> list[dict[str, Any]]:
    with _connection() as connection:
        rows = connection.execute("SELECT job_id,gpu_hours,gpu_count,started_at,completed_at FROM cloud_usage WHERE account_id=? AND completed_at IS NOT NULL AND report_status='pending'", (account_id,)).fetchall()
    return [{"job_id": row[0], "gpu_hours": row[1], "gpu_count": row[2], "started_at": row[3], "completed_at": row[4]} for row in rows]


def mark_reported(job_id: str, status: str) -> None:
    with _connection() as connection:
        connection.execute("UPDATE cloud_usage SET report_status=? WHERE job_id=?", (status, job_id))

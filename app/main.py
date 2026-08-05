"""Farm Manager FastAPI application entrypoint.

Run with:
    uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routers import artifacts, audit, cloud, gpu_discovery, health, jobs, monitoring, pools, tags, websocket, workers
from app.audit_log import record as record_audit
from fastapi.staticfiles import StaticFiles
from pathlib import Path

settings = get_settings()

app = FastAPI(
    title="GPU Farm Manager",
    description="Central controller for the DrunkenBot GPU Farm (local + cloud workflows).",
    version="0.1.0",
)

# The dashboard is same-origin in production. Explicit origins keep a separate
# development UI usable without exposing the API to arbitrary web pages.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.parsed_cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(workers.router)
app.include_router(jobs.router)
app.include_router(pools.router)
app.include_router(tags.router)
app.include_router(gpu_discovery.router)
app.include_router(websocket.router)
app.include_router(monitoring.router)
app.include_router(artifacts.router)
app.include_router(cloud.router)
app.include_router(audit.router)
dashboard_dir = Path(__file__).parent / "dashboard"
if dashboard_dir.exists():
    app.mount("/dashboard", StaticFiles(directory=dashboard_dir, html=True), name="dashboard")


@app.middleware("http")
async def audit_operator_mutations(request: Request, call_next):
    """Record sensitive operator mutations without retaining request bodies."""
    response = await call_next(request)
    path = request.url.path
    sensitive = (
        (path == "/jobs" and request.method == "POST") or
        path in {"/pause-all", "/resume-all", "/stop-all"} or
        (path.startswith("/jobs/") and request.method == "POST") or
        (path.startswith("/pools") and request.method in {"POST", "PUT", "DELETE"}) or
        (path.startswith("/tags") and request.method in {"PUT", "POST", "DELETE"}) or
        (path.startswith("/gpu-discovery") and request.method in {"PUT", "POST", "DELETE"})
    )
    if sensitive:
        record_audit("operator-token" if request.headers.get("x-farm-admin-token") else "local-operator", request.method, path, response.status_code, request.client.host if request.client else None)
    return response


@app.get("/")
def root() -> dict:
    """Return basic service info."""

    return {"service": "gpu-farm-manager", "farm_mode": settings.farm_mode}

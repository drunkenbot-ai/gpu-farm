"""Farm Manager FastAPI application entrypoint.

Run with:
    uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routers import health, jobs, pools, websocket, workers

settings = get_settings()

app = FastAPI(
    title="GPU Farm Manager",
    description="Central controller for the DrunkenBot GPU Farm (local + cloud workflows).",
    version="0.1.0",
)

# Dashboard SPA (Phase 9) will be served from a different origin during
# development; restrict this before shipping to production origins only.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(workers.router)
app.include_router(jobs.router)
app.include_router(pools.router)
app.include_router(websocket.router)


@app.get("/")
def root() -> dict:
    """Return basic service info."""

    return {"service": "gpu-farm-manager", "farm_mode": settings.farm_mode}

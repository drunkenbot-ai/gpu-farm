# gpu-farm
DrunkenBot GPU farm services

See [goals.md](goals.md) for the full project spec.

## Architecture

This project wraps and extends the coordinator/worker foundation already
built in the `engine` submodule (`drunkenbot-ai/engine`, shared with
LLM-IDE) rather than re-implementing job orchestration from scratch:

- `engine.coordinator.JobManager` / `engine.contracts` -- worker
  register/heartbeat/claim/progress/complete/fail protocol and job state.
- `app/` (this repo) -- FastAPI Farm Manager backend: modern HTTP + WebSocket
  API around the job manager, resource pools/tags (in progress), and the
  local/cloud entitlement split.

Local GPU Farm mode (`FARM_MODE=local`) never contacts any licensing
service. Cloud GPU Farm mode (`FARM_MODE=cloud`) validates a GPU-hours API
key against `drunkenbot-ai/cloud-service`'s `/auth/validate-key` before
admitting cloud jobs/workers.

## Setup

```powershell
git submodule update --init --recursive
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

## Run

```powershell
uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
```

- `GET /health` -- farm status summary
- `GET /workers`, `POST /register`, `POST /heartbeat`, `POST /stale-workers`
- `GET /jobs`, `POST /claim-job`, `POST /progress`, `POST /complete`,
  `POST /fail`, `POST /pause-all`, `POST /resume-all`, `POST /stop-all`
- `WS /ws` -- real-time worker/job event stream for dashboards
- `GET /pools` -- placeholder (resource pools/tagging land in a later phase)

## Status

Early scaffold. See the project plan for phased rollout: GPU discovery/
validation, GPU selection persistence, resource pools & tagging, local/cloud
workflows, monitoring history, file distribution with delta sync, the web
dashboard, and the packaged Windows worker-client EXE are not implemented
yet.

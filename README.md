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
- `GET /jobs` -- list all known training jobs
- `POST /jobs` -- submit a new training job (`{"job": <TrainingJobSpec>,
  "resource_pool_id": str?}`); cloud jobs require the same
  `Authorization: Bearer` key as cloud worker registration
- `GET /jobs/schedule-preview` -- dry-run the scheduler for hypothetical
  requirements (`backend`, `min_vram_gb`, `resource_pool_id`), showing
  every worker's current eligibility and why not
- `POST /claim-job`, `POST /progress`, `POST /complete`, `POST /fail`,
  `POST /pause-all`, `POST /resume-all`, `POST /stop-all`
- `GET /gpu-discovery` -- detect + validate GPUs on the Farm Manager's own
  machine (name, vendor, VRAM, CUDA version, compute capability, driver,
  PCI id, utilization, temperature, power)
- `POST /gpu-discovery/validate` -- validate GPU records a remote worker
  self-reported at registration time
- `GET /gpu-discovery/{worker_id}/selection` -- validated GPUs for a worker
  annotated with a stable `identifier` and current `selected` state
  (defaults to "all validated GPUs" until an explicit choice is saved)
- `PUT /gpu-discovery/{worker_id}/selection` -- persist which validated
  GPUs join the farm (`{"selected": [<identifier>, ...]}`); selections
  survive Farm Manager restarts
- `POST /gpu-discovery/local/register` -- (re-)register the Farm Manager's
  own machine as worker `local`, using only its currently selected,
  validated GPUs
- `WS /ws` -- real-time worker/job event stream for dashboards
- `GET /monitoring/history` -- durable worker heartbeat and training-progress history
- `GET /cloud/status`, `POST /cloud/report-usage` -- cloud entitlement, local GPU-hour ledger, and safe replay of completed usage to cloud-service
- `GET/PUT /artifacts/{path}` -- SHA-256 manifest (`/manifest`), HTTP Range download and resumable upload
- `GET /artifacts/projects/{project_id}/tree-manifest` -- file-hash project manifest used by workers for changed-files-only synchronization
- `GET/POST /pools`, `GET/PUT/DELETE /pools/{id}` -- Resource Pool CRUD;
  each pool response includes live `stats` (GPU/available/busy counts,
  total VRAM, average utilization) and resolved `gpus`
- `POST /pools/{id}/members`, `DELETE /pools/{id}/members/{worker_id}/{identifier}`
  -- manually add/remove one GPU from a pool (on top of any rule-based membership)
- `GET /tags` -- every farm GPU with its combined auto-derived (vendor,
  model, CUDA major, VRAM bucket) + manually-assigned tags
- `GET/PUT /tags/workers/{worker_id}`, `GET/PUT /tags/workers/{worker_id}/gpus/{identifier}`
  -- view/persist manual tags for a worker or one of its GPUs

Worker registration (`POST /register`) enforces goals.md's "only validated
GPUs can participate in the farm" rule: if a worker reports GPUs under
`capabilities.extra.gpus` and none pass validation (NVIDIA + CUDA + ≥4GB
VRAM + healthy driver), registration is rejected with HTTP 422.

GPU selection (`app/gpu_selection.py`) is a separate concern layered on top
of validation: an operator can further narrow a worker's *validated* GPUs
down to the subset that should actually join the farm (individual,
multiple, or all), persisted per worker in
`~/.drunkenbot_ide/gpu_farm/gpu_selection.json`.

Resource Pools (`app/pools.py`) and tags (`app/tagging.py`) operate on the
farm-wide GPU inventory (`app/gpu_inventory.py`), built from every
registered worker's joined GPUs. A pool's membership is the union of
explicitly added GPUs and any GPU matching all of the pool's rules (vendor,
model, compute capability, VRAM size, driver version, machine, tags), so a
GPU can belong to multiple pools at once. Pool/tag data is persisted at
`~/.drunkenbot_ide/gpu_farm/pools.json` and `.../tags.json`.

The scheduler (`app/scheduler.py`) layers goals.md section 6's remaining
requirements on top of the engine's own backend/VRAM/tag claim matching:
resource pool selection, live CPU/RAM/disk/GPU utilization thresholds
(`SCHEDULER_MAX_*`/`SCHEDULER_MIN_*` env vars), and local-vs-cloud
entitlement. A worker that is nominally "available" but reports
utilization/CPU/RAM/disk past the configured limit on a `/claim-job` poll
is told there's no job for it (without touching the engine's queue),
preventing over-allocation onto an already-saturated machine.

## Status

The core private-farm and cloud-farm workflows are implemented and verified.
Real training jobs have completed end-to-end in both modes: submit → worker
claim → verified project sync → engine training → telemetry/progress → output
upload → completion. Cloud GPU-hour usage is reported through the sibling
`cloud-service`'s idempotent `/auth/report-usage` endpoint.

The manager persists telemetry history, performs changed-files-only project
sync with resumable and hash-verified transfer, includes a live dashboard,
and has a packaged Windows tray-worker EXE build path. See [plan.md](plan.md)
for the remaining production-hardening and product-completeness work.

## Worker and dashboard

Open `http://localhost:8080/dashboard/` for the live dashboard. Run a real
local worker with `python -m app.worker_client --manager http://localhost:8080`
(`--mode cloud --api-key <key>` claims cloud jobs). Build the no-Python-required Windows
binary with `pyinstaller --noconfirm worker.spec`; the executable is emitted
under `dist/GPUFarmWorker/` (or `dist/GPUFarmWorker.exe`, depending on the
PyInstaller mode).

The packaged worker starts as a Windows tray app. Run it with
`--install-autostart` to register per-user Windows startup, or
`--remove-autostart` to remove that registration. Build reproducibly with
`powershell -ExecutionPolicy Bypass -File scripts/build_worker.ps1 -Clean`.

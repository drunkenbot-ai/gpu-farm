GPU Farm Manager — Implementation Plan

Repo survey findings (why this plan looks the way it does)

gpu-farm repo (this project): empty scaffold, just README/LICENSE/goals.md.
Everything below is new work here.

LLM-IDE (engine/) already has a working coordinator/worker foundation —
this is NOT a greenfield build, it's infrastructure-around-an-existing-system:
engine/contracts/ — protocol messages (register/heartbeat/claim/progress/
  complete/fail), TrainingJobSpec, WorkerAvailability, WorkerCapabilities.
engine/coordinator/ — JobManager (in-memory + JSON state_store),
  CoordinatorApiServer (plain threaded HTTP, polling-based, **no WebSockets,
  no auth, no web UI**), artifacts.py (full-zip bundle upload/download,
  no delta sync, no resume).
engine/worker/ — RemoteWorkerClient, detect_worker_capabilities()
  (currently coarse — device string + total_vram_gb only, no GPU name/
  vendor/CUDA version/driver/temperature/PCI id).
engine/runpod_cloud.py — existing RunPod-based cloud GPU provisioning
  (spin up rented pods). This is a different cloud mechanism than goals.md's
  "cloud pool with subscription GPU-hours" — keep both, don't conflate them.
engine/telemetry_store.py — per-run SQLite metrics history already exists
  for training curves, but it's local-to-a-run, not farm-wide.
engine/license_client.py — IDE's own signed-license-at-launch pattern
  (Ed25519 receipt + offline grace cache). Reusable pattern, but it's IDE
  per-version licensing, not the GPU-hours subscription check.
Scheduling today: job_manager_impl.py only compares total_vram_gb from
  capabilities — no CPU/RAM/disk/pool/tag awareness yet.

cloud-service already has the licensing/quota building block:
POST /auth/validate-key — validates a bearer API key, checks account +
  key status, returns tier and quota_gpu_hours_per_month. This is
  exactly the entitlement check goals.md wants for the Cloud GPU Farm
  workflow.
Gap: no GPU-hours consumption/decrement endpoint yet — only issuance
  and validation. Cloud Farm Manager will need to report usage back
  (e.g. POST /auth/report-usage) so quota actually depletes.
/license/validate is IDE-launch licensing, unrelated to farm GPU-hours.

Strategy

Build gpu-farm as a new service that wraps and extends engine.coordinator
/ engine.worker rather than re-implementing job orchestration from scratch,
and integrates with cloud-service only for the Cloud workflow's entitlement
check + usage reporting. Local workflow never talks to cloud-service.

Phases

Phase 1 — Farm Manager backend (web app)
FastAPI service in gpu-farm importing engine.coordinator/engine.contracts
  as a dependency (or vendored subset) instead of the bare http.server API.
Add WebSocket channel for live worker/job/telemetry push (replace polling).
New DB (Postgres/SQLite via SQLAlchemy) for: workers, GPUs, resource pools,
  tags, job history, telemetry history (farm-wide, not per-run), pool
  membership rules.
Local/Cloud mode toggle at the Farm Manager level; Cloud mode gates on
  cloud-service /auth/validate-key before admitting cloud workers/jobs.

Phase 2 — GPU discovery & validation
New module (pynvml + nvidia-smi fallback) collecting: name, vendor, VRAM,
  CUDA version, compute capability, driver version, PCI ID, utilization,
  temperature, power.
Validation gate: NVIDIA + CUDA + ≥4GB VRAM + healthy runtime + compatible
  driver before a GPU can register.
Extend WorkerCapabilities/WorkerDescriptor.capabilities to carry this
  richer payload (currently only total_vram_gb).

Phase 3 — GPU selection & persistence
Worker-side config (per-machine) listing selected GPU indices; persists
  across restarts; only selected GPUs get registered with the coordinator.

Phase 4 — Resource Pools & Tagging
New data model: Pool (manual or rule-based membership by CUDA version,
  vendor, model, series, compute capability, VRAM, driver, machine, tags,
  project), Tag (many-to-many on GPU/worker).
Scheduler extended to target pools, not raw GPUs; pool-aware placement
  alongside existing VRAM check.

Phase 5 — Local GPU Farm workflow
Local mode: register/claim/heartbeat flow with zero calls to cloud-service.
Reuses existing engine.coordinator protocol as-is for this path.

Phase 6 — Cloud GPU Farm workflow
Cloud mode: Farm Manager validates API key via cloud-service
  /auth/validate-key before accepting cloud jobs/workers; tracks GPU-hours
  consumed against quota_gpu_hours_per_month; needs a new usage-reporting
  endpoint added to cloud-service (out of scope for gpu-farm repo alone —
  coordinate change there).
Enforce expiration/limits; block cloud pool use on invalid entitlement.

Phase 7 — Monitoring & telemetry
Workers stream CPU/RAM/disk/network/GPU telemetry continuously over the
  new WebSocket channel; Farm Manager persists history for dashboard graphs
  (separate from engine.telemetry_store's per-run training curves).

Phase 8 — File & project distribution
Extend engine.coordinator.artifacts bundle mechanism with delta sync
  (hash-diff changed files only) and resumable chunked upload/download;
  keep integrity verification.

Phase 9 — Web Dashboard (frontend)
Modern SPA (React/Vite or similar) consuming the WebSocket + REST API:
  worker list/status, GPU stats, job controls (submit/start/pause/resume/
  stop/cancel/restart/logs/download), pool management UI, farm stats,



Handoff status (as of Phases 1-6 complete, PR #1 opened to main)

Done and verified against real hardware (GTX 1650 in this sandbox)
Phase 1 — FastAPI scaffold on the engine submodule; FARM_MODE=local|cloud
  toggle; WebSocket dashboard stream; health/workers/jobs/pools routers.
Phase 2 — app/gpu_discovery.py: nvidia-smi/pynvml/torch three-tier
  detection + validation (NVIDIA + CUDA + ≥4GB VRAM + known driver);
  registration rejects (422) worker if all reported GPUs fail validation.
  Fixed an upstream engine bug along the way (_restore_envelope import,
  engine PR #3, merged, submodule bumped).
Phase 3 — app/gpu_selection.py: per-worker JSON-persisted GPU
  selection (UUID > PCI id > index stable identifiers); local/register
  manages the Farm Manager's own host as a worker using only selected GPUs.
Phase 4 — app/pools.py + app/tagging.py + app/gpu_inventory.py:
  full Resource Pool CRUD (rule-based + manual membership, union semantics,
  live stats) and auto/manual GPU & worker tags.
Phases 5-6 — app/routers/jobs.py POST /jobs (job submission was
  entirely missing before this) + app/scheduler.py (resource pool
  selection, live CPU/RAM/disk/GPU utilization thresholds, local/cloud
  entitlement, resource-health gate on /claim-job to prevent
  over-allocation). GET /jobs/schedule-preview dry-runs eligibility.

All of the above is committed on branch ncj-dneg-verbose-guacamole /
PR #1 in drunkenbot-ai/gpu-farm, not yet merged to main.

Known gaps / things the next agent should know before continuing
No automated test suite exists in either gpu-farm or the engine
  submodule. All verification so far has been live manual testing against
  real hardware/a running server (see commit messages for exact steps). If
  the next agent needs regression safety, consider adding pytest +
  httpx.AsyncClient-based API tests before extending further — none exist
  today, so don't assume any.
Resource pool → job assignment is single-worker only. engine's
  RuntimeSpec.preferred_worker_id only supports pinning one worker per
  job. When a Resource Pool resolves to more than one eligible worker at
  submission time, POST /jobs currently just records the pool id +
  eligible worker list in job.metadata for visibility but does not
  restrict which worker can claim it — any worker matching backend/VRAM/tags
  can claim it regardless of pool membership. Multi-worker pool-scoped
  claiming would need either an engine protocol change (e.g. an
  allowed_worker_ids list on RuntimeSpec) or a Farm-Manager-side gate in
  POST /claim-job that checks pool membership before forwarding to
  manager.handle_claim_job() (mirror the resource-health gate pattern
  already there).
cuda_version is always null in GPU discovery output because the
  venv's torch build is CPU-only (torch.version.cuda is unset). Detection
  still works correctly via nvidia-smi independent of torch; this only
  affects the informational cuda_version field, not validation. A worker
  EXE build (Phase 10) should ship a CUDA-matched torch wheel.
Coordinator state is shared with any local LLM-IDE install on the same
  machine (~/.drunkenbot_ide/coordinator_state.sqlite3) — expect
  pre-existing "local" workers/jobs from other apps/sessions when testing
  live; this is by design (goals.md wants the farm to manage the same local
  machine LLM-IDE already trains on), not a bug.
Multi-GPU training jobs are explicitly out of scope so far (goals.md
  section 6 says "support future multi-GPU training jobs" — future work,
  not required yet). RuntimeSpec/TrainingJobSpec are single-device.

Recommended order for the next agent
Per goals.md, the remaining sections are 9 (Local workflow), 10 (Cloud
workflow), 11 (Monitoring), 12 (File/project distribution), 13 (Packaging/
worker EXE), 14 (Architecture — mostly descriptive, no new work), 15
(Future expansion — no work yet). Suggested order, each phase should be
verified live (not just unit-tested) against this sandbox's real GPU
before moving on, same as phases 1-6:

Phase 9/10 — Local & Cloud end-to-end workflows (goals.md sections
   9-10). This is the highest-value next step: prove a full round trip
   (submit job → local/remote worker claims → runs the actual engine
   training backend, not a mock → progress streams over /ws → completes
   → artifact retrievable) for FARM_MODE=local, then repeat for
   FARM_MODE=cloud with a real (or stubbed, if cloud-service isn't
   reachable) entitlement check and confirm cloud-only gating (workers/jobs
   requiring Authorization: Bearer when cloud) behaves correctly.
   Watch for: engine's in-process local training path
   (JobManagerCore/backends registry) vs the remote-worker HTTP path —
   confirm which one local/register + /claim-job actually exercises
   end-to-end, since so far this session only exercised registration/claim
   plumbing, not an actual training run to completion.
Phase 11 — Monitoring & telemetry: persist farm-wide history (worker
   CPU/RAM/disk/GPU, job progress) beyond the current point-in-time
   /health//workers//jobs snapshots and the live /ws stream — e.g. a
   lightweight SQLite time-series table, distinct from
   engine.telemetry_store's per-run training curves. Expose a
   GET /monitoring/history (or similar) for the dashboard to chart.
Phase 12 — File & project distribution: extend
   engine.coordinator.artifacts's full-zip bundle mechanism with delta
   sync (hash-diff changed files only) and resumable chunked
   upload/download, per goals.md section 5's "download only changed files
   on future runs" and "support resumable downloads" requirements — neither
   is implemented yet; today's artifact transfer is full-zip-only
   (inherited as-is from engine).
Phase 13/9 (dashboard) and Phase 10 (Windows EXE worker client)
   come last per the original plan ordering, once the API surface above is
   stable — building UI/packaging against a moving API is wasted effort.

Before starting any of the above
Read goals.md sections 9-12 in full (they weren't re-read in detail
  during this session beyond the summaries in the "Repo survey findings"
  section above).
git submodule update --init --recursive and reactivate the .venv
  (all deps already listed in requirements.txt).
Confirm PR #1 has been reviewed/merged, or continue on top of it if still
  open, to avoid diverging history.

  license/subscription status banner for cloud mode.

Phase 10 — Python Worker Client packaging (Windows EXE)
System tray app (pystray or similar) wrapping engine.worker.RemoteWorkerClient:
  auto-start with Windows, connect/authenticate/heartbeat, GPU select UI,
  start/pause/resume/stop/cancel controls.
Package with PyInstaller, mirroring LLM-IDE/packaging/packager.py's
  pattern (private runtime bundling, no user-facing Python/.py files),
  as its own installer separate from the IDE installer. Add update-check path.

Open questions to confirm before/while building
Farm Manager backend: FastAPI (matches cloud-service's stack) — confirm.
Should gpu-farm depend on LLM-IDE as a git submodule/package, or
   vendor a copy of engine.coordinator/engine.contracts/engine.worker?
Who owns the new cloud-service usage-reporting endpoint — done in this
   session against the cloud-service project, or tracked separately?
Priority order — recommend Phase 1 → 2 → 5 (local end-to-end first) →
   3/4 → 9/10 → 6/7/8, since a working local farm is the stated initial goal.

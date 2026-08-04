# Next Steps — Handoff Plan for the Next Agent

_Status as of Phases 1-6 complete (PR #1, branch `ncj-dneg-verbose-guacamole`)._

## Done and verified against real hardware (GTX 1650 sandbox)

- **Phase 1** — FastAPI scaffold on the `engine` submodule; `FARM_MODE=local|cloud`
  toggle; WebSocket dashboard stream; health/workers/jobs/pools routers.
- **Phase 2** — `app/gpu_discovery.py`: nvidia-smi/pynvml/torch three-tier
  detection + validation (NVIDIA + CUDA + ≥4GB VRAM + known driver);
  registration rejects (422) a worker if all reported GPUs fail validation.
  Fixed an upstream `engine` bug along the way (`_restore_envelope` import,
  engine PR #3, merged, submodule bumped).
- **Phase 3** — `app/gpu_selection.py`: per-worker JSON-persisted GPU
  selection (UUID > PCI id > index stable identifiers); `local/register`
  manages the Farm Manager's own host as a worker using only selected GPUs.
- **Phase 4** — `app/pools.py` + `app/tagging.py` + `app/gpu_inventory.py`:
  full Resource Pool CRUD (rule-based + manual membership, union semantics,
  live stats) and auto/manual GPU & worker tags.
- **Phases 5-6** — `app/routers/jobs.py` `POST /jobs` (job submission was
  entirely missing before this) + `app/scheduler.py` (resource pool
  selection, live CPU/RAM/disk/GPU utilization thresholds, local/cloud
  entitlement, resource-health gate on `/claim-job` to prevent
  over-allocation). `GET /jobs/schedule-preview` dry-runs eligibility.

## Known gaps / things to know before continuing

- **No automated test suite exists** in either `gpu-farm` or the `engine`
  submodule. All verification so far has been live manual testing against
  a running server on real hardware (see commit messages for exact steps).
  Consider adding `pytest` + `httpx.AsyncClient`-based API tests before
  extending further — none exist today.
- **Resource pool → job assignment is single-worker only.** `engine`'s
  `RuntimeSpec.preferred_worker_id` only supports pinning one worker per
  job. When a Resource Pool resolves to more than one eligible worker at
  submission time, `POST /jobs` records the pool id + eligible worker list
  in `job.metadata` for visibility but does **not** restrict which worker
  can claim it — any worker matching backend/VRAM/tags can claim it
  regardless of pool membership. Multi-worker pool-scoped claiming needs
  either an `engine` protocol change (e.g. an `allowed_worker_ids` list on
  `RuntimeSpec`) or a Farm-Manager-side gate in `POST /claim-job` that
  checks pool membership before forwarding to `manager.handle_claim_job()`
  (mirror the resource-health gate pattern already there).
- **`cuda_version` is always null** in GPU discovery output because the
  venv's torch build is CPU-only (`torch.version.cuda` is unset). Detection
  still works correctly via `nvidia-smi` independent of torch; this only
  affects the informational `cuda_version` field, not validation. A worker
  EXE build (later phase) should ship a CUDA-matched torch wheel.
- **Coordinator state is shared with any local LLM-IDE install** on the
  same machine (`~/.drunkenbot_ide/coordinator_state.sqlite3`) — expect
  pre-existing "local" workers/jobs from other apps/sessions when testing
  live; this is by design (the farm manages the same local machine
  LLM-IDE already trains on), not a bug.
- **Multi-GPU training jobs** are explicitly out of scope so far (future
  work per goals.md). `RuntimeSpec`/`TrainingJobSpec` are single-device.

## Recommended order for the next agent

Per `goals.md`, the remaining sections are 9 (Local workflow), 10 (Cloud
workflow), 11 (Monitoring), 12 (File/project distribution), 13
(Packaging/worker EXE), 14 (Architecture — descriptive), 15 (Future
expansion — no work yet). Verify each phase live against real hardware
before moving on, same as Phases 1-6:

1. **Phase 9/10 — Local & Cloud end-to-end workflows.** Highest-value next
   step: prove a full round trip (submit job → local/remote worker claims →
   runs the actual `engine` training backend, not a mock → progress streams
   over `/ws` → completes → artifact retrievable) for `FARM_MODE=local`,
   then repeat for `FARM_MODE=cloud` with a real (or stubbed, if
   cloud-service isn't reachable) entitlement check, confirming cloud-only
   gating (`Authorization: Bearer` required) behaves correctly. Confirm
   which of `engine`'s in-process local training path vs remote-worker HTTP
   path `local/register` + `/claim-job` actually exercises end-to-end —
   this session only verified registration/claim plumbing, not an actual
   training run to completion.
2. **Phase 11 — Monitoring & telemetry.** Persist farm-wide history (worker
   CPU/RAM/disk/GPU, job progress) beyond the current point-in-time
   snapshots and live `/ws` stream — e.g. a lightweight SQLite time-series
   table, distinct from `engine.telemetry_store`'s per-run training curves.
   Expose a `GET /monitoring/history` (or similar) for the dashboard.
3. **Phase 12 — File & project distribution.** Extend
   `engine.coordinator.artifacts`'s full-zip bundle mechanism with delta
   sync (hash-diff changed files only) and resumable chunked
   upload/download, per goals.md's "download only changed files on future
   runs" and "support resumable downloads" requirements — neither is
   implemented yet; artifact transfer today is full-zip-only (inherited
   as-is from `engine`).
4. **Dashboard (web UI) and Windows EXE worker client** come last, once the
   API surface above is stable — building UI/packaging against a moving
   API is wasted effort.

## Before starting any of the above

- Read `goals.md` sections 9-12 in full.
- `git submodule update --init --recursive` and reactivate the `.venv`
  (all deps already listed in `requirements.txt`).
- Confirm PR #1 has been reviewed/merged, or continue on top of it if
  still open, to avoid diverging history.

# GPU Farm Manager — Implementation Plan and Handoff

## Current implementation status

The Farm Manager, worker protocol, and cloud-service usage endpoint are now
implemented across `gpu-farm`, its `engine` submodule, and the sibling
`cloud-service` checkout.

### Completed and verified

1. **Farm Manager and scheduling** — FastAPI REST/WebSocket API, GPU discovery
   and validation, persisted GPU selection, tags, pools, resource-health
   scheduling, local/cloud modes, and per-job pause/resume/cancel/restart.
   Coordinator state is stored with the farm rather than in a user profile.
2. **Real local training** — A worker performs submit → claim → verified
   project sync → real engine training → progress telemetry → output upload →
   completion. This was verified through `scripts/e2e_smoke.py`.
3. **Cloud workflow** — API-key-gated cloud workers/jobs, a durable manager
   GPU-hour ledger, pre-dispatch quota reservations, and replayable reporting.
   Sibling `cloud-service` now provides authenticated, quota-enforced,
   idempotent `POST /auth/reserve-usage`, `/auth/release-reservation`, and
   `/auth/report-usage`.
   A local cross-service cloud job completed and reported usage successfully.
4. **Monitoring and distribution** — SQLite history captures CPU/RAM/disk/
   network/GPU heartbeat snapshots and progress. Hash manifests, HTTP Range
   resume, output uploads, and changed-files-only project synchronization are
   implemented; ZIP transfer remains a compatibility fallback.
5. **Dashboard and worker packaging** — `/dashboard/` shows health, workers,
   jobs, telemetry, and job controls. The Windows tray worker supports
   per-user autostart. `scripts/build_worker.ps1` builds `GPUFarmWorker.exe`;
   a ~210 MB EXE was produced.
6. **Production hardening baseline** — Farm Manager has configurable explicit
   CORS origins, optional `FARM_ADMIN_TOKEN` protection for job mutations,
   Windows Credential Manager storage for cloud worker keys, and an Alembic
   baseline for telemetry/cloud usage tables. Operator mutations are retained
   in a protected, durable audit trail.
7. **Tests** — `gpu-farm` has five passing FastAPI regression tests;
   `cloud-service` has 36 passing tests, including GPU-hour quota,
   idempotency coverage.

## Remaining work

### Production hardening

1. Extend Farm Manager and cloud-service migration chains to cover future
   coordinator state changes. Both services now have an Alembic baseline.
2. Extend optional Farm Manager token protection into full operator roles and
   require it in production deployment configuration. Basic audit logging is
   complete; role identity and richer audit details remain.
3. Add retry/backoff, visibility, and alerts for failed cloud usage reports
   and reservation releases. The Farm Manager deliberately does not persist
   customer API keys, so an authenticated caller supplies one for early hold
   release on cancellation/failure.

### Product completeness

1. Add dashboard GPU-tag editing, filtering, and telemetry charts. Submission,
   pool creation/deletion, output downloads, and cloud entitlement display are
   complete.
2. Add tray configuration screens for manager URL, API-key storage, and GPU
   selection. The existing tray host handles lifecycle/autostart only.
3. Sign the Inno Setup Windows installer and run the clean-machine EXE smoke
   test. Installer build scripts and a hash-verified release-manifest update
   check are complete; certificate-backed Authenticode signing and a clean
   Windows test host remain.
4. Implement multi-GPU/multi-worker jobs and strict multi-member pool claim
   enforcement. Current jobs are single-worker and broad pool matching is
   advisory unless it resolves to exactly one worker.
5. Add telemetry retention/downsampling, graph-ready aggregates, output
   retention, and cache-eviction policies.

## Repository boundaries

- Commit `engine/` worker/coordinator changes in its own repository, then
  update the parent submodule pointer.
- Commit `cloud-service` usage-reporting changes independently.
- Ignore local smoke-test artifacts and SQLite state files.

## Suggested next order

1. Commit the engine, cloud-service, and GPU Farm changes intentionally.
2. Add cloud-service migrations and complete operator roles/auditing.
3. Package/sign/test the worker on a clean Windows machine.
4. Finish dashboard UX and multi-GPU scheduling.

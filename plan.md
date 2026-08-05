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
   GPU-hour ledger, and replayable reporting. Sibling `cloud-service` now
   provides authenticated, quota-enforced, idempotent `POST /auth/report-usage`.
   A local cross-service cloud job completed and reported usage successfully.
4. **Monitoring and distribution** — SQLite history captures CPU/RAM/disk/
   network/GPU heartbeat snapshots and progress. Hash manifests, HTTP Range
   resume, output uploads, and changed-files-only project synchronization are
   implemented; ZIP transfer remains a compatibility fallback.
5. **Dashboard and worker packaging** — `/dashboard/` shows health, workers,
   jobs, telemetry, and job controls. The Windows tray worker supports
   per-user autostart. `scripts/build_worker.ps1` builds `GPUFarmWorker.exe`;
   a ~210 MB EXE was produced.
6. **Tests** — `gpu-farm` has four passing FastAPI regression tests;
   `cloud-service` has 34 passing tests, including GPU-hour quota and
   idempotency coverage.

## Remaining work

### Production hardening

1. Add Alembic migrations to both services; SQLite `create_all` is only a
   local-development migration strategy.
2. Configure restrictive CORS and Farm Manager authentication/authorization.
3. Move worker cloud keys from command-line arguments to Windows Credential
   Manager or another secure secret-delivery mechanism.
4. Add retry/backoff, visibility, and alerts for failed cloud usage reports.
5. Add cloud quota reservation/release before dispatch. Current reporting
   debits after completion, so it cannot reserve capacity across managers.

### Product completeness

1. Expand the dashboard: submission UI, pool/tag editors, filtering, charts,
   output download links, and cloud entitlement display.
2. Add tray configuration screens for manager URL, API-key storage, and GPU
   selection. The existing tray host handles lifecycle/autostart only.
3. Add signed installer, update path, and clean-machine EXE smoke test.
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
2. Add migrations, secure configuration, and cloud quota reservations.
3. Package/sign/test the worker on a clean Windows machine.
4. Finish dashboard UX and multi-GPU scheduling.

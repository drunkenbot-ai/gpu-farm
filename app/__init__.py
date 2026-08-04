"""GPU Farm Manager backend (FastAPI).

Wraps the `engine.coordinator.JobManager` / `engine.contracts` protocol
(from the `engine` submodule, shared with LLM-IDE) with a modern HTTP+WS API,
persistence, resource pools/tags, and the local/cloud entitlement split
described in goals.md.
"""

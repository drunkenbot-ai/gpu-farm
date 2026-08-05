from __future__ import annotations

from fastapi.testclient import TestClient


def _client(monkeypatch, tmp_path) -> TestClient:
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'farm.sqlite3'}")
    monkeypatch.setenv("ARTIFACT_ROOT", str(tmp_path / "artifacts"))
    from app.config import get_settings
    from app.job_manager import get_job_manager
    get_settings.cache_clear(); get_job_manager.cache_clear()
    from app.main import app
    return TestClient(app)


def test_artifact_manifest_and_range_resume(monkeypatch, tmp_path) -> None:
    client = _client(monkeypatch, tmp_path)
    assert client.put("/artifacts/nested/blob.bin", content=b"0123456789").status_code == 200
    manifest = client.get("/artifacts/nested/blob.bin/manifest").json()
    assert manifest["size"] == 10 and len(manifest["sha256"]) == 64
    response = client.get("/artifacts/nested/blob.bin", headers={"Range": "bytes=3-6"})
    assert response.status_code == 206
    assert response.content == b"3456"
    assert response.headers["content-range"] == "bytes 3-6/10"


def test_project_tree_manifest(monkeypatch, tmp_path) -> None:
    client = _client(monkeypatch, tmp_path)
    assert client.put("/artifacts/projects/demo/dataset/a.txt", content=b"a").status_code == 200
    assert client.put("/artifacts/projects/demo/dataset/b.txt", content=b"b").status_code == 200
    manifest = client.get("/artifacts/projects/demo/tree-manifest").json()
    assert [entry["path"] for entry in manifest["files"]] == ["dataset/a.txt", "dataset/b.txt"]


def test_heartbeat_persists_history(monkeypatch, tmp_path) -> None:
    client = _client(monkeypatch, tmp_path)
    response = client.post("/heartbeat", json={"worker_id": "test-worker", "availability": "available", "backend": "local", "device": "cpu", "metrics": {"cpu_percent": 12.5}})
    assert response.status_code == 200
    samples = client.get("/monitoring/history?worker_id=test-worker").json()["samples"]
    assert samples[-1]["payload"]["cpu_percent"] == 12.5


def test_cloud_usage_ledger_tracks_pending_completion(monkeypatch, tmp_path) -> None:
    _client(monkeypatch, tmp_path)
    from app.cloud_usage import complete, pending, start, summary
    start("cloud-job", "account-1", gpu_count=2)
    assert complete("cloud-job") >= 0
    state = summary("account-1")
    assert state["usage_records"] == 1 and state["pending_reports"] == 1
    assert pending("account-1")[0]["gpu_count"] == 2


def test_operator_token_protects_job_mutations(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("FARM_ADMIN_TOKEN", "test-operator-secret")
    client = _client(monkeypatch, tmp_path)
    assert client.post("/pause-all").status_code == 401
    assert client.post("/pause-all", headers={"X-Farm-Admin-Token": "test-operator-secret"}).status_code == 200
    events = client.get("/audit", headers={"X-Farm-Admin-Token": "test-operator-secret"}).json()["events"]
    assert events[-1]["path"] == "/pause-all" and events[-1]["status_code"] == 200

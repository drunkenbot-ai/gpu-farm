"""Submit and execute a tiny real CPU training job against a running manager.

Usage: python scripts/e2e_smoke.py http://127.0.0.1:8091
"""
from __future__ import annotations

import json
import sys
import argparse
from pathlib import Path
from urllib.request import Request, urlopen

import numpy as np
from tokenizers import Tokenizer, models, pre_tokenizers

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.config import ModelConfig, TrainingConfig
from engine.contracts import TrainingJobSpec
from engine.worker import WorkerClientConfig, run_worker_client


def post(base: str, path: str, payload: dict) -> dict:
    request = Request(f"{base}{path}", data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"}, method="POST")
    with urlopen(request, timeout=30) as response:
        return json.loads(response.read())


def _post_authorized(base: str, path: str, payload: dict, api_key: str) -> dict:
    request = Request(f"{base}{path}", data=json.dumps(payload).encode(), headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}, method="POST")
    with urlopen(request, timeout=30) as response:
        return json.loads(response.read())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("manager", nargs="?", default="http://127.0.0.1:8080")
    parser.add_argument("--mode", choices=("local", "cloud"), default="local")
    parser.add_argument("--api-key")
    args = parser.parse_args()
    base = args.manager.rstrip("/")
    root = Path("artifacts/e2e_smoke").resolve(); dataset = root / "dataset"; dataset.mkdir(parents=True, exist_ok=True)
    tokenizer = Tokenizer(models.WordLevel({"<pad>": 0, "<unk>": 1, "<bos>": 2, "<eos>": 3, **{str(i): i + 4 for i in range(30)}}, unk_token="<unk>"))
    tokenizer.pre_tokenizer = pre_tokenizers.Whitespace(); tokenizer.save(str(dataset / "tokenizer.json"))
    np.save(dataset / "train_tokens.npy", np.arange(128, dtype=np.int64) % 34)
    np.save(dataset / "val_tokens.npy", np.arange(64, dtype=np.int64) % 34)
    (dataset / "dataset_summary.json").write_text("{}", encoding="utf-8")
    training = TrainingConfig(output_dir=root / "manager_output", epochs=1, batch_size=1, sample_stride=8,
        eval_interval=1000, save_interval=1000, data_loader_workers=0, use_amp=False, precision="fp32", device="cpu", resume=False)
    job = TrainingJobSpec.local(dataset, ModelConfig(vocab_size=32, context_length=8, embedding_size=16, head_count=1, layer_count=1), training)
    if args.mode == "cloud":
        from engine.contracts import BackendKind
        job.runtime.backend = BackendKind.CLOUD
    submitted = post(base, "/jobs", {"job": job.to_jsonable()}) if not args.api_key else _post_authorized(base, "/jobs", {"job": job.to_jsonable()}, args.api_key)
    print(f"submitted {submitted['job_id']}")
    # Earlier interrupted smoke runs can leave a queued job behind; drain a
    # small bounded number of claims without ever looping indefinitely.
    for _ in range(3):
        run_worker_client(WorkerClientConfig(coordinator_url=base, worker_id="e2e-training-worker", backend=job.runtime.backend, api_key=args.api_key, execute_jobs=True, claim_once=True,
            workspace_dir=root / "worker_workspace"))
    with urlopen(f"{base}/jobs", timeout=30) as response:
        jobs = json.loads(response.read())["jobs"]
    current = next(item for item in jobs if item["spec"]["job_id"] == submitted["job_id"])
    print(json.dumps({"job_id": submitted["job_id"], "status": current["spec"]["status"], "result": current.get("result")}, indent=2))
    if current["spec"]["status"] != "completed":
        raise SystemExit("E2E training job did not complete")


if __name__ == "__main__":
    main()

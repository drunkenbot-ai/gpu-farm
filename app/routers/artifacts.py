"""Project/result artifact serving with SHA-256 manifests and HTTP range resume."""
from __future__ import annotations

import hashlib
import json
import mimetypes
import re
from pathlib import Path
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from app.config import get_settings

router = APIRouter(prefix="/artifacts", tags=["artifacts"])

def _path(value: str) -> Path:
    root = Path(get_settings().artifact_root).resolve()
    candidate = (root / value).resolve()
    if root not in candidate.parents and candidate != root:
        raise HTTPException(400, "Artifact path escapes artifact root")
    return candidate

def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

@router.get("/{artifact_path:path}/manifest")
def manifest(artifact_path: str) -> dict:
    path = _path(artifact_path)
    if not path.is_file(): raise HTTPException(404, "Artifact not found")
    return {"path": artifact_path, "size": path.stat().st_size, "sha256": _sha256(path), "chunk_size": 1024 * 1024}

@router.get("/{artifact_path:path}/tree-manifest")
def tree_manifest(artifact_path: str) -> dict:
    directory = _path(artifact_path)
    if not directory.is_dir(): raise HTTPException(404, "Artifact project not found")
    files = []
    for item in sorted(directory.rglob("*")):
        if item.is_file():
            files.append({"path": item.relative_to(directory).as_posix(), "size": item.stat().st_size, "sha256": _sha256(item)})
    return {"path": artifact_path, "files": files}

@router.get("/{artifact_path:path}")
def download(artifact_path: str, request: Request):
    path = _path(artifact_path)
    if not path.is_file(): raise HTTPException(404, "Artifact not found")
    size = path.stat().st_size; header = request.headers.get("range")
    if not header: return FileResponse(path, media_type=mimetypes.guess_type(str(path))[0] or "application/octet-stream", headers={"Accept-Ranges":"bytes", "ETag": _sha256(path)})
    match = re.fullmatch(r"bytes=(\d+)-(\d*)", header)
    if not match: raise HTTPException(416, "Invalid range")
    start, end = int(match.group(1)), int(match.group(2) or size - 1)
    if start >= size or end < start: raise HTTPException(416, "Range not satisfiable")
    end = min(end, size - 1)
    with path.open("rb") as stream:
        stream.seek(start); body = stream.read(end - start + 1)
    return Response(body, 206, media_type="application/octet-stream", headers={"Content-Range":f"bytes {start}-{end}/{size}", "Content-Length":str(len(body)), "Accept-Ranges":"bytes", "ETag":_sha256(path)})

@router.put("/{artifact_path:path}")
async def upload(artifact_path: str, request: Request) -> dict:
    path = _path(artifact_path); path.parent.mkdir(parents=True, exist_ok=True)
    content_range = request.headers.get("content-range")
    body = await request.body()
    if content_range:
        match = re.fullmatch(r"bytes (\d+)-(\d+)/(\d+)", content_range)
        if not match: raise HTTPException(400, "Invalid Content-Range")
        start, end, total = map(int, match.groups())
        if end - start + 1 != len(body): raise HTTPException(400, "Content-Range length mismatch")
        mode = "r+b" if path.exists() else "wb"
        with path.open(mode) as stream: stream.seek(start); stream.write(body)
        complete = path.stat().st_size >= total
    else:
        path.write_bytes(body); complete = True
    return {"status":"ok", "artifact_url":f"/artifacts/{artifact_path}", "complete":complete, "size":path.stat().st_size, "sha256":_sha256(path) if complete else None}

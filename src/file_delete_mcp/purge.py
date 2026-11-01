from __future__ import annotations

import json
import os
import shutil
import stat
import time
from dataclasses import dataclass, field
from datetime import datetime

from .trash import BATCH_RE, DEL_DIR_NAME, FILES_DIR, MANIFEST_NAME, TrashError


@dataclass
class BatchInfo:
    batch_id: str
    path: str
    created_at: float
    files: int
    bytes: int
    flags: list[str] = field(default_factory=list)


def del_dir_path(root: str) -> str:
    return os.path.join(root, DEL_DIR_NAME)


def list_batches(root: str) -> list[BatchInfo]:
    del_dir = del_dir_path(root)
    if not os.path.isdir(del_dir):
        return []
    batches: list[BatchInfo] = []
    for name in os.listdir(del_dir):
        path = os.path.join(del_dir, name)
        if not BATCH_RE.match(name) or os.path.islink(path) or not os.path.isdir(path):
            continue
        batches.append(read_batch(path, name))
    return sorted(batches, key=lambda batch: (batch.created_at, batch.batch_id))


def read_batch(path: str, batch_id: str) -> BatchInfo:
    created = os.path.getmtime(path)
    manifest = os.path.join(path, MANIFEST_NAME)
    if os.path.isfile(manifest):
        try:
            with open(manifest, encoding="utf-8") as handle:
                data = json.load(handle)
            entries = data["entries"]
            files = sum(int(entry["files"]) for entry in entries)
            total = sum(int(entry["bytes"]) for entry in entries)
            created = datetime.fromisoformat(data["created_at"]).timestamp()
            return BatchInfo(batch_id, path, created, files, total)
        except (OSError, ValueError, TypeError, KeyError):
            pass
    files, total = scan_batch(path)
    return BatchInfo(batch_id, path, created, files, total)


def scan_batch(path: str) -> tuple[int, int]:
    base = os.path.join(path, FILES_DIR)
    if not os.path.isdir(base):
        base = path
    files = 0
    total = 0
    for root, _dirs, names in os.walk(base, followlinks=False):
        for name in names:
            try:
                stat_result = os.lstat(os.path.join(root, name))
            except OSError:
                continue
            files += 1
            total += stat_result.st_size
    return files, total


def select_batches(
    root: str,
    batch_ids: list[str] | None = None,
    older_than_days: int | None = None,
    all_batches: bool = False,
) -> list[BatchInfo]:
    batches = list_batches(root)
    if all_batches:
        return batches
    selected: list[BatchInfo] = []
    if batch_ids:
        known = {batch.batch_id: batch for batch in batches}
        for batch_id in batch_ids:
            batch = known.get(batch_id)
            if batch is None:
                raise TrashError(f"unknown batch: {batch_id}")
            if batch not in selected:
                selected.append(batch)
    if older_than_days is not None:
        cutoff = time.time() - older_than_days * 86400
        for batch in batches:
            if batch.created_at <= cutoff and batch not in selected:
                selected.append(batch)
    return selected


def purge_batches(batches: list[BatchInfo]) -> list[dict]:
    results: list[dict] = []
    for batch in batches:
        try:
            shutil.rmtree(batch.path, onexc=_on_rm_error)
        except OSError as exc:
            results.append(
                {
                    "batch_id": batch.batch_id,
                    "status": "error",
                    "files": batch.files,
                    "bytes": batch.bytes,
                    "reason": str(exc),
                }
            )
            continue
        results.append(
            {
                "batch_id": batch.batch_id,
                "status": "purged",
                "files": batch.files,
                "bytes": batch.bytes,
            }
        )
    return results


def _on_rm_error(function, path, _error) -> None:
    try:
        os.chmod(path, stat.S_IWRITE)
    except OSError:
        pass
    function(path)

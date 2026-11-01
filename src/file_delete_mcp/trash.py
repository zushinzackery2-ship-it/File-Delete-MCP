from __future__ import annotations

import json
import os
import re
import shutil
import threading
import uuid
from datetime import datetime, timezone

from .paths import ResolvedPath, is_junction

DEL_DIR_NAME = ".del"
MANIFEST_NAME = "manifest.json"
FILES_DIR = "files"
BATCH_RE = re.compile(r"^[0-9]{8}T[0-9]{6}-[0-9a-f]{6}$")

_lock = threading.RLock()


class TrashError(ValueError):
    pass


def ensure_del_dir(root: str) -> str:
    del_dir = os.path.join(root, DEL_DIR_NAME)
    if os.path.lexists(del_dir):
        if os.path.islink(del_dir) or is_junction(del_dir) or not os.path.isdir(del_dir):
            raise TrashError(".del exists but is not a real directory")
    else:
        os.makedirs(del_dir)
    ignore = os.path.join(del_dir, ".gitignore")
    if not os.path.exists(ignore):
        with open(ignore, "w", encoding="utf-8") as handle:
            handle.write("*\n")
    return del_dir


def new_batch_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    return f"{stamp}-{uuid.uuid4().hex[:6]}"


def write_manifest(batch_dir: str, payload: dict) -> None:
    target = os.path.join(batch_dir, MANIFEST_NAME)
    temp = target + ".tmp"
    with open(temp, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
    os.replace(temp, target)


def move_entry(root: str, batch_id: str, item: ResolvedPath, files: int, size: int) -> dict:
    with _lock:
        del_dir = ensure_del_dir(root)
        batch_dir = os.path.join(del_dir, batch_id)
        destination = os.path.join(batch_dir, FILES_DIR, item.rel.replace("/", os.sep))
        os.makedirs(os.path.dirname(destination), exist_ok=True)
        shutil.move(item.abs_path, destination)
    return {
        "entry_id": f"{batch_id}:{item.rel}",
        "original_rel": item.rel,
        "kind": item.kind,
        "files": files,
        "bytes": size,
        "moved_at": datetime.now(timezone.utc).isoformat(),
    }

from __future__ import annotations

import os
from dataclasses import dataclass


class PathError(ValueError):
    pass


@dataclass(frozen=True)
class ResolvedPath:
    input: str
    abs_path: str
    key: str
    rel: str
    kind: str
    exists: bool


def is_junction(path: str) -> bool:
    checker = getattr(os.path, "isjunction", None)
    return bool(checker and checker(path))


def norm_key(path: str) -> str:
    return os.path.normcase(os.path.abspath(path))


def is_within(root_key: str, target_key: str) -> bool:
    if target_key == root_key:
        return True
    prefix = root_key.rstrip("\\/") + os.sep
    return target_key.startswith(prefix)


def detect_kind(path: str) -> str:
    if os.path.islink(path):
        return "symlink"
    if is_junction(path):
        return "junction"
    if os.path.isdir(path):
        return "dir"
    if os.path.isfile(path):
        return "file"
    return "other"


def resolve_input(root: str, raw: str) -> ResolvedPath:
    if not raw or not raw.strip():
        raise PathError("empty path")
    text = raw.strip()
    candidate = text if os.path.isabs(text) else os.path.join(root, text)
    abs_path = os.path.abspath(candidate)
    key = norm_key(abs_path)
    root_key = norm_key(root)
    if key == root_key:
        raise PathError("refusing to delete the workspace root")
    if not is_within(root_key, key):
        raise PathError(f"outside workspace: {text}")
    parent_real = os.path.normcase(os.path.realpath(os.path.dirname(abs_path)))
    root_real = os.path.normcase(os.path.realpath(root))
    if not is_within(root_real, parent_real):
        raise PathError(f"parent directory escapes workspace: {text}")
    exists = os.path.lexists(abs_path)
    kind = detect_kind(abs_path) if exists else "missing"
    rel = os.path.relpath(abs_path, root).replace(os.sep, "/")
    return ResolvedPath(text, abs_path, key, rel, kind, exists)


def dedupe_nested(items: list[ResolvedPath]) -> list[ResolvedPath]:
    kept: list[ResolvedPath] = []
    for item in sorted(items, key=lambda value: len(value.key)):
        if any(is_within(parent.key, item.key) for parent in kept):
            continue
        kept.append(item)
    return kept


def dir_stats(path: str) -> tuple[int, int, int]:
    count = 0
    total = 0
    newest = 0
    for base, dirs, files in os.walk(path, followlinks=False):
        for name in files:
            try:
                stat = os.lstat(os.path.join(base, name))
            except OSError:
                continue
            count += 1
            total += stat.st_size
            newest = max(newest, stat.st_mtime_ns)
        for name in dirs:
            child = os.path.join(base, name)
            if not (os.path.islink(child) or is_junction(child)):
                continue
            try:
                stat = os.lstat(child)
            except OSError:
                continue
            count += 1
            newest = max(newest, stat.st_mtime_ns)
    return count, total, newest


def fingerprint(path: str, kind: str) -> tuple:
    stat = os.lstat(path)
    if kind == "dir":
        count, total, newest = dir_stats(path)
        return ("dir", count, total, newest)
    return (kind, stat.st_size, stat.st_mtime_ns)

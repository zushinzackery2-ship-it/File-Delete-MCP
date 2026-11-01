from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass, field

from .paths import ResolvedPath, dir_stats, is_within, norm_key

MAX_FILES = 200
MAX_BYTES = 50 * 1024 * 1024


@dataclass
class EntryReport:
    input: str
    resolved: str
    kind: str
    files: int
    bytes: int
    rel: str
    key: str
    flags: list[str] = field(default_factory=list)


@dataclass
class RiskReport:
    entries: list[EntryReport] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    risk: str = "ok"
    totals: dict = field(default_factory=dict)


def measure(item: ResolvedPath) -> tuple[int, int]:
    if item.kind == "dir":
        count, total, _ = dir_stats(item.abs_path)
        return count, total
    try:
        return 1, os.lstat(item.abs_path).st_size
    except OSError:
        return 0, 0


def git_dirty(root: str, rel: str) -> bool:
    if not os.path.isdir(os.path.join(root, ".git")):
        return False
    git = shutil.which("git")
    if not git:
        return False
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    try:
        proc = subprocess.run(
            [git, "-C", root, "status", "--porcelain", "--", rel],
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=flags,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return proc.returncode == 0 and bool(proc.stdout.strip())


def analyze_trash(root: str, del_dir: str, items: list[ResolvedPath], recursive: bool) -> RiskReport:
    report = RiskReport()
    del_key = norm_key(del_dir)
    git_key = norm_key(os.path.join(root, ".git"))
    if os.path.lexists(del_dir) and not os.path.isdir(del_dir):
        report.blockers.append(".del exists but is not a directory")
    for item in items:
        if item.kind == "missing":
            report.blockers.append(f"missing: {item.input}")
            continue
        if item.key == git_key:
            report.blockers.append("refusing to trash the repository .git directory")
            continue
        if is_within(del_key, item.key):
            report.blockers.append(f"refusing to trash .del itself: {item.input}")
            continue
        files, size = measure(item)
        if item.kind == "dir" and files and not recursive:
            report.blockers.append(f"non-empty directory needs recursive=true: {item.input}")
            continue
        flags = collect_flags(root, item, files, size)
        report.entries.append(
            EntryReport(
                input=item.input,
                resolved=item.abs_path,
                kind=item.kind,
                files=files,
                bytes=size,
                rel=item.rel,
                key=item.key,
                flags=flags,
            )
        )
        report.warnings.extend(f"{flag}: {item.input}" for flag in flags)
    report.risk = "block" if report.blockers else ("warn" if report.warnings else "ok")
    report.totals = {
        "entries": len(report.entries),
        "files": sum(entry.files for entry in report.entries),
        "bytes": sum(entry.bytes for entry in report.entries),
    }
    return report


def collect_flags(root: str, item: ResolvedPath, files: int, size: int) -> list[str]:
    flags: list[str] = []
    if files > MAX_FILES:
        flags.append("many-files")
    if size > MAX_BYTES:
        flags.append("large")
    if ".git" in item.rel.split("/"):
        flags.append("git-metadata")
    if git_dirty(root, item.rel):
        flags.append("git-dirty")
    return flags


def analyze_purge(batches: list) -> RiskReport:
    report = RiskReport()
    for batch in batches:
        flags: list[str] = []
        if batch.files > MAX_FILES:
            flags.append("many-files")
        if batch.bytes > MAX_BYTES:
            flags.append("large")
        report.warnings.extend(f"{flag}: {batch.batch_id}" for flag in flags)
    report.risk = "warn" if report.warnings else "ok"
    report.totals = {
        "entries": len(batches),
        "files": sum(batch.files for batch in batches),
        "bytes": sum(batch.bytes for batch in batches),
    }
    return report

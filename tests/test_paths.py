from __future__ import annotations

import os
from pathlib import Path

import pytest

from file_delete_mcp.paths import (
    PathError,
    dedupe_nested,
    fingerprint,
    is_within,
    resolve_input,
)


def test_resolves_relative_path(workspace: Path) -> None:
    target = workspace / "a.txt"
    target.write_text("x", encoding="utf-8")
    item = resolve_input(str(workspace), "a.txt")
    assert item.abs_path == str(target)
    assert item.rel == "a.txt"
    assert item.kind == "file"


def test_rejects_outside_workspace(workspace: Path) -> None:
    with pytest.raises(PathError):
        resolve_input(str(workspace), "../outside.txt")


def test_rejects_workspace_root(workspace: Path) -> None:
    with pytest.raises(PathError):
        resolve_input(str(workspace), ".")


def test_rejects_symlinked_parent_escape(workspace: Path, tmp_path_factory: pytest.TempPathFactory) -> None:
    outside = tmp_path_factory.mktemp("outside")
    link = workspace / "link"
    try:
        os.symlink(outside, link, target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation is not permitted")
    with pytest.raises(PathError):
        resolve_input(str(workspace), "link/file.txt")


def test_dedupes_nested_paths(workspace: Path) -> None:
    (workspace / "src").mkdir()
    (workspace / "src" / "a.py").write_text("x", encoding="utf-8")
    items = [
        resolve_input(str(workspace), "src/a.py"),
        resolve_input(str(workspace), "src"),
    ]
    kept = dedupe_nested(items)
    assert [item.rel for item in kept] == ["src"]


def test_fingerprint_changes_with_content(workspace: Path) -> None:
    target = workspace / "a.txt"
    target.write_text("one", encoding="utf-8")
    before = fingerprint(str(target), "file")
    target.write_text("two", encoding="utf-8")
    stat = target.stat()
    os.utime(target, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000))
    after = fingerprint(str(target), "file")
    assert before != after


def test_is_within_handles_case_and_prefix(workspace: Path) -> None:
    root = os.path.normcase(str(workspace))
    assert is_within(root, os.path.normcase(str(workspace / "child")))
    assert not is_within(root, os.path.normcase(str(workspace) + "-sibling"))

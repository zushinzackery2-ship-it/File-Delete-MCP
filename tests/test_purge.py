from __future__ import annotations

import os
import stat
import time
from pathlib import Path

import pytest

from file_delete_mcp.purge import list_batches, purge_batches, select_batches
from file_delete_mcp.trash import TrashError


def make_batch(workspace: Path, batch_id: str, name: str = "a.txt") -> Path:
    batch = workspace / ".del" / batch_id / "files"
    batch.mkdir(parents=True)
    (batch / name).write_text("x", encoding="utf-8")
    return workspace / ".del" / batch_id


def test_select_all_batches(workspace: Path) -> None:
    make_batch(workspace, "20260101T000000-aaaaaa")
    make_batch(workspace, "20260102T000000-bbbbbb")
    batches = select_batches(str(workspace), all_batches=True)
    assert len(batches) == 2


def test_select_unknown_batch_raises(workspace: Path) -> None:
    with pytest.raises(TrashError):
        select_batches(str(workspace), batch_ids=["20990101T000000-abcdef"])


def test_select_older_than_days(workspace: Path) -> None:
    old = make_batch(workspace, "20260101T000000-aaaaaa")
    make_batch(workspace, "20260102T000000-bbbbbb")
    past = time.time() - 10 * 86400
    os.utime(old, (past, past))
    batches = select_batches(str(workspace), older_than_days=5)
    assert [batch.batch_id for batch in batches] == ["20260101T000000-aaaaaa"]


def test_purge_removes_read_only_file(workspace: Path) -> None:
    batch = make_batch(workspace, "20260101T000000-aaaaaa")
    target = batch / "files" / "a.txt"
    os.chmod(target, stat.S_IREAD)
    batches = list_batches(str(workspace))
    results = purge_batches(batches)
    assert results[0]["status"] == "purged"
    assert not batch.exists()

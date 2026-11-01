from __future__ import annotations

import os
from pathlib import Path

import pytest

from file_delete_mcp import policy
from file_delete_mcp.service import Service, ServiceError
from file_delete_mcp.tickets import TicketError


def write_file(workspace: Path, name: str, content: str = "x") -> Path:
    target = workspace / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return target


def test_trash_then_purge_roundtrip(service: Service, workspace: Path) -> None:
    target = write_file(workspace, "a.txt")
    preview = service.preview("trash", ["a.txt"])
    assert preview["risk"] == "ok"
    assert preview["ticket"]

    result = service.trash(["a.txt"], False, preview["ticket"])
    assert result["totals"]["moved"] == 1
    assert not target.exists()
    batch_id = result["batch_id"]
    assert (workspace / ".del" / batch_id / "files" / "a.txt").exists()
    assert (workspace / ".del" / batch_id / "manifest.json").exists()

    purge_preview = service.preview("purge", all_batches=True)
    assert purge_preview["ticket"]
    purge_result = service.purge(None, None, True, purge_preview["ticket"])
    assert purge_result["totals"]["purged"] == 1
    assert not (workspace / ".del" / batch_id).exists()


def test_absolute_path_is_supported(service: Service, workspace: Path) -> None:
    target = write_file(workspace, "a.txt")
    preview = service.preview("trash", [str(target)])
    assert preview["risk"] == "ok"
    result = service.trash([str(target)], False, preview["ticket"])
    assert result["totals"]["moved"] == 1


def test_ticket_is_single_use(service: Service, workspace: Path) -> None:
    write_file(workspace, "a.txt")
    preview = service.preview("trash", ["a.txt"])
    service.trash(["a.txt"], False, preview["ticket"])
    with pytest.raises(TicketError):
        service.trash(["a.txt"], False, preview["ticket"])


def test_path_mismatch_is_refused(service: Service, workspace: Path) -> None:
    write_file(workspace, "a.txt")
    write_file(workspace, "b.txt")
    preview = service.preview("trash", ["a.txt"])
    with pytest.raises(TicketError):
        service.trash(["b.txt"], False, preview["ticket"])


def test_stale_preview_is_refused(service: Service, workspace: Path) -> None:
    target = write_file(workspace, "a.txt")
    preview = service.preview("trash", ["a.txt"])
    stat = target.stat()
    os.utime(target, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000))
    with pytest.raises(TicketError):
        service.trash(["a.txt"], False, preview["ticket"])


def test_non_empty_directory_needs_recursive(service: Service, workspace: Path) -> None:
    target = write_file(workspace, "dir/a.txt")
    blocked = service.preview("trash", ["dir"])
    assert blocked["risk"] == "block"
    assert blocked["ticket"] is None

    preview = service.preview("trash", ["dir"], recursive=True)
    assert preview["ticket"]
    result = service.trash(["dir"], True, preview["ticket"])
    assert result["totals"]["moved"] == 1
    assert not target.exists()


def test_outside_and_root_are_blocked(service: Service) -> None:
    assert service.preview("trash", ["../outside.txt"])["risk"] == "block"
    assert service.preview("trash", ["."])["risk"] == "block"


def test_del_itself_is_blocked(service: Service, workspace: Path) -> None:
    (workspace / ".del").mkdir()
    preview = service.preview("trash", [".del"])
    assert preview["risk"] == "block"


def test_missing_path_is_blocked(service: Service) -> None:
    preview = service.preview("trash", ["nope.txt"])
    assert preview["risk"] == "block"


def test_warning_requires_acknowledgement(
    service: Service, workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(policy, "MAX_FILES", 0)
    write_file(workspace, "a.txt")
    preview = service.preview("trash", ["a.txt"])
    assert preview["risk"] == "warn"
    with pytest.raises(TicketError):
        service.trash(["a.txt"], False, preview["ticket"])

    preview = service.preview("trash", ["a.txt"])
    result = service.trash(["a.txt"], False, preview["ticket"], accept_warnings=True)
    assert result["totals"]["moved"] == 1


def test_purge_requires_selector(service: Service) -> None:
    with pytest.raises(ServiceError):
        service.preview("purge")


def test_purge_unknown_batch_is_blocked(service: Service) -> None:
    preview = service.preview("purge", batch_ids=["20990101T000000-abcdef"])
    assert preview["risk"] == "block"
    assert preview["ticket"] is None


def test_purge_selection_change_is_refused(service: Service, workspace: Path) -> None:
    write_file(workspace, "a.txt")
    first = service.preview("trash", ["a.txt"])
    service.trash(["a.txt"], False, first["ticket"])
    purge_preview = service.preview("purge", all_batches=True)

    write_file(workspace, "b.txt")
    second = service.preview("trash", ["b.txt"])
    service.trash(["b.txt"], False, second["ticket"])

    with pytest.raises(TicketError):
        service.purge(None, None, True, purge_preview["ticket"])


def test_invalid_scope_is_rejected(service: Service) -> None:
    with pytest.raises(ServiceError):
        service.preview("unknown")

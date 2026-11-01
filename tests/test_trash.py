from __future__ import annotations

from pathlib import Path

from file_delete_mcp.paths import resolve_input
from file_delete_mcp.trash import ensure_del_dir, move_entry, new_batch_id


def test_ensure_del_dir_creates_gitignore(workspace: Path) -> None:
    del_dir = Path(ensure_del_dir(str(workspace)))
    assert del_dir == workspace / ".del"
    assert (del_dir / ".gitignore").read_text(encoding="utf-8") == "*\n"


def test_move_entry_keeps_relative_layout(workspace: Path) -> None:
    target = workspace / "src" / "a.py"
    target.parent.mkdir()
    target.write_text("x", encoding="utf-8")
    item = resolve_input(str(workspace), "src/a.py")
    batch_id = new_batch_id()
    entry = move_entry(str(workspace), batch_id, item, 1, 1)
    moved = workspace / ".del" / batch_id / "files" / "src" / "a.py"
    assert moved.read_text(encoding="utf-8") == "x"
    assert not target.exists()
    assert entry["original_rel"] == "src/a.py"
    assert entry["entry_id"] == f"{batch_id}:src/a.py"

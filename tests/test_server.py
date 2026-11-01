from __future__ import annotations

import asyncio
from pathlib import Path

from file_delete_mcp import server
from file_delete_mcp.config import Config
from file_delete_mcp.service import Service


def test_exactly_three_tools() -> None:
    tools = asyncio.run(server.mcp.list_tools())
    assert sorted(tool.name for tool in tools) == ["preview_delete", "purge_del", "trash_paths"]


def test_preview_tool_uses_configured_service(workspace: Path) -> None:
    target = workspace / "a.txt"
    target.write_text("x", encoding="utf-8")
    server.set_service(Service(Config(root=workspace, ticket_ttl_seconds=300)))
    result = server.preview_delete("trash", ["a.txt"])
    assert result["ticket"]
    assert result["risk"] == "ok"

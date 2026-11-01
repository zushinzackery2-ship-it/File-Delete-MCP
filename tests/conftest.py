from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from file_delete_mcp.config import Config
from file_delete_mcp.service import Service


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    return tmp_path


@pytest.fixture
def service(workspace: Path) -> Service:
    return Service(Config(root=workspace, ticket_ttl_seconds=300))

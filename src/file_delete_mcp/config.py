from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DEL_DIR_NAME = ".del"


@dataclass(frozen=True)
class Config:
    root: Path
    ticket_ttl_seconds: int = 300

    @property
    def del_dir(self) -> Path:
        return self.root / DEL_DIR_NAME


def load_config(root: str | None = None, ticket_ttl_seconds: int = 300) -> Config:
    raw = root or os.environ.get("FILE_DELETE_ROOT") or os.getcwd()
    resolved = Path(os.path.realpath(os.path.abspath(raw)))
    if not resolved.is_dir():
        raise ValueError(f"workspace root is not a directory: {resolved}")
    if ticket_ttl_seconds <= 0:
        raise ValueError("ticket TTL must be positive")
    return Config(root=resolved, ticket_ttl_seconds=ticket_ttl_seconds)

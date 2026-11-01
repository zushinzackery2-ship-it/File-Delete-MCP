from __future__ import annotations

import argparse
import warnings

warnings.filterwarnings(
    "ignore",
    message="Field 'lifespan' has an incomplete definition.*",
    module=r"pydantic_settings\..*",
)

from mcp.server.fastmcp import FastMCP

from .config import load_config
from .service import Service

mcp = FastMCP(
    "file-delete",
    instructions=(
        "Workspace-scoped deletion. Call preview_delete before any destructive action; "
        "trash_paths and purge_del reject calls without a matching, unexpired ticket."
    ),
)

_service_instance: Service | None = None


def set_service(service: Service) -> None:
    global _service_instance
    _service_instance = service


def _service() -> Service:
    global _service_instance
    if _service_instance is None:
        _service_instance = Service(load_config())
    return _service_instance


@mcp.tool()
def preview_delete(
    scope: str,
    paths: list[str] | None = None,
    recursive: bool = False,
    batch_ids: list[str] | None = None,
    older_than_days: int | None = None,
    all: bool = False,
) -> dict:
    """Validate a delete request and issue a one-time ticket.

    scope="trash" previews moving paths into the workspace .del directory; set
    recursive=true to allow non-empty directories. scope="purge" previews
    permanently deleting .del batches selected by batch_ids, older_than_days,
    or all=true. A blocked request returns risk="block" and no ticket.
    """
    return _service().preview(scope, paths, recursive, batch_ids, older_than_days, all)


@mcp.tool()
def trash_paths(
    paths: list[str],
    ticket: str,
    recursive: bool = False,
    accept_warnings: bool = False,
) -> dict:
    """Move previewed paths into the workspace .del directory.

    The ticket must come from preview_delete with scope="trash" and the same
    paths and recursive flag. Paths or files changed after preview are refused.
    """
    return _service().trash(paths, recursive, ticket, accept_warnings)


@mcp.tool()
def purge_del(
    ticket: str,
    batch_ids: list[str] | None = None,
    older_than_days: int | None = None,
    all: bool = False,
    accept_warnings: bool = False,
) -> dict:
    """Permanently delete .del batches selected by the matching purge preview.

    The ticket must come from preview_delete with scope="purge". Batches added
    or changed after preview are refused.
    """
    return _service().purge(batch_ids, older_than_days, all, ticket, accept_warnings)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="file-delete-mcp")
    parser.add_argument("--root", default=None, help="workspace root; defaults to the current directory")
    parser.add_argument("--ticket-ttl", type=int, default=300, help="ticket lifetime in seconds")
    args = parser.parse_args(argv)
    set_service(Service(load_config(args.root, args.ticket_ttl)))
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()

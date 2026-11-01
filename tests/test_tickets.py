from __future__ import annotations

import time

import pytest

from file_delete_mcp.tickets import TicketError, TicketStore


def test_ticket_is_one_time() -> None:
    store = TicketStore(ttl_seconds=60)
    token = store.issue("trash", "root", {"paths": []}, "ok", [])
    ticket = store.take(token)
    assert ticket.scope == "trash"
    with pytest.raises(TicketError):
        store.take(token)


def test_ticket_expires() -> None:
    store = TicketStore(ttl_seconds=0.01)
    token = store.issue("trash", "root", {"paths": []}, "ok", [])
    time.sleep(0.03)
    with pytest.raises(TicketError):
        store.take(token)


def test_unknown_ticket_is_rejected() -> None:
    store = TicketStore(ttl_seconds=60)
    with pytest.raises(TicketError):
        store.take("missing")

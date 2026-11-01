from __future__ import annotations

import secrets
import threading
import time
from dataclasses import dataclass, field


class TicketError(ValueError):
    pass


@dataclass
class Ticket:
    token: str
    scope: str
    root: str
    expires_at: float
    payload: dict
    risk: str
    warnings: list[str] = field(default_factory=list)


class TicketStore:
    def __init__(self, ttl_seconds: float) -> None:
        self._ttl = ttl_seconds
        self._lock = threading.Lock()
        self._items: dict[str, Ticket] = {}

    def issue(self, scope: str, root: str, payload: dict, risk: str, warnings: list[str]) -> str:
        with self._lock:
            self._sweep()
            token = secrets.token_urlsafe(18)
            expires_at = time.monotonic() + self._ttl
            self._items[token] = Ticket(token, scope, root, expires_at, payload, risk, list(warnings))
            return token

    def take(self, token: str) -> Ticket:
        with self._lock:
            self._sweep()
            ticket = self._items.pop(token, None)
            if ticket is None:
                raise TicketError("unknown, expired, or already used ticket")
            return ticket

    def _sweep(self) -> None:
        now = time.monotonic()
        expired = [token for token, ticket in self._items.items() if ticket.expires_at <= now]
        for token in expired:
            del self._items[token]

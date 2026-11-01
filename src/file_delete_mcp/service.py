from __future__ import annotations

import os
import shutil
from datetime import datetime, timezone

from .config import Config
from .paths import PathError, ResolvedPath, dedupe_nested, fingerprint, resolve_input
from .policy import EntryReport, analyze_purge, analyze_trash, measure
from .purge import purge_batches, select_batches
from .tickets import Ticket, TicketError, TicketStore
from .trash import TrashError, ensure_del_dir, move_entry, new_batch_id, write_manifest


class ServiceError(ValueError):
    pass


class Service:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.tickets = TicketStore(config.ticket_ttl_seconds)

    def preview(
        self,
        scope: str,
        paths: list[str] | None = None,
        recursive: bool = False,
        batch_ids: list[str] | None = None,
        older_than_days: int | None = None,
        all_batches: bool = False,
    ) -> dict:
        if scope == "trash":
            return self._preview_trash(paths or [], recursive)
        if scope == "purge":
            return self._preview_purge(batch_ids or [], older_than_days, all_batches)
        raise ServiceError("scope must be 'trash' or 'purge'")

    def trash(
        self,
        paths: list[str],
        recursive: bool,
        ticket: str,
        accept_warnings: bool = False,
    ) -> dict:
        if not paths:
            raise ServiceError("paths must not be empty")
        root = str(self.config.root)
        claim = self.tickets.take(ticket)
        self._check_claim(claim, "trash")
        items = self._resolve_for_apply(root, paths)
        if sorted(item.key for item in items) != claim.payload["paths"]:
            raise TicketError("paths do not match the previewed ticket")
        if bool(recursive) != claim.payload["recursive"]:
            raise TicketError("recursive does not match the previewed ticket")
        self._require_warning_ack(claim, accept_warnings)
        self._verify_trash_fingerprints(claim, items)
        return self._execute_trash(root, items)

    def purge(
        self,
        batch_ids: list[str] | None,
        older_than_days: int | None,
        all_batches: bool,
        ticket: str,
        accept_warnings: bool = False,
    ) -> dict:
        if not batch_ids and older_than_days is None and not all_batches:
            raise ServiceError("purge needs batch_ids, older_than_days, or all=true")
        root = str(self.config.root)
        claim = self.tickets.take(ticket)
        self._check_claim(claim, "purge")
        try:
            batches = select_batches(root, batch_ids, older_than_days, bool(all_batches))
        except TrashError as exc:
            raise TicketError(str(exc)) from exc
        if sorted(batch.batch_id for batch in batches) != claim.payload["batch_ids"]:
            raise TicketError("batch selection changed since preview")
        self._require_warning_ack(claim, accept_warnings)
        for batch in batches:
            expected = claim.payload["fingerprints"].get(batch.batch_id)
            if expected is None or self._fingerprint_batch(batch.path) != expected:
                raise TicketError(f"batch changed since preview: {batch.batch_id}")
        results = purge_batches(batches)
        return {
            "results": results,
            "totals": {
                "purged": sum(1 for item in results if item["status"] == "purged"),
                "failed": sum(1 for item in results if item["status"] == "error"),
                "files": sum(item["files"] for item in results if item["status"] == "purged"),
                "bytes": sum(item["bytes"] for item in results if item["status"] == "purged"),
            },
        }

    def _preview_trash(self, paths: list[str], recursive: bool) -> dict:
        if not paths:
            raise ServiceError("paths must not be empty")
        root = str(self.config.root)
        resolved: list[ResolvedPath] = []
        blockers: list[str] = []
        for raw in paths:
            try:
                resolved.append(resolve_input(root, str(raw)))
            except PathError as exc:
                blockers.append(str(exc))
        items = dedupe_nested(resolved)
        report = analyze_trash(root, str(self.config.del_dir), items, bool(recursive))
        blockers.extend(report.blockers)
        fingerprints: dict[str, tuple] = {}
        for item in items:
            if not item.exists or item.kind == "missing":
                continue
            try:
                fingerprints[item.key] = fingerprint(item.abs_path, item.kind)
            except OSError as exc:
                blockers.append(f"cannot read {item.input}: {exc}")
        risk = "block" if blockers else report.risk
        payload = {
            "paths": sorted(item.key for item in items),
            "recursive": bool(recursive),
            "fingerprints": fingerprints,
        }
        ticket = None
        if risk != "block":
            ticket = self.tickets.issue("trash", root, payload, risk, report.warnings)
        return {
            "scope": "trash",
            "ticket": ticket,
            "risk": risk,
            "blockers": blockers,
            "warnings": report.warnings,
            "entries": [self._entry_dict(entry) for entry in report.entries],
            "totals": report.totals,
            "expires_in_seconds": self.config.ticket_ttl_seconds,
        }

    def _preview_purge(self, batch_ids: list[str], older_than_days: int | None, all_batches: bool) -> dict:
        if not batch_ids and older_than_days is None and not all_batches:
            raise ServiceError("purge needs batch_ids, older_than_days, or all=true")
        if older_than_days is not None and older_than_days < 0:
            raise ServiceError("older_than_days must be >= 0")
        root = str(self.config.root)
        blockers: list[str] = []
        try:
            batches = select_batches(root, batch_ids, older_than_days, bool(all_batches))
        except TrashError as exc:
            batches = []
            blockers.append(str(exc))
        if not batches and not blockers:
            blockers.append("no .del batches match the selector")
        report = analyze_purge(batches)
        fingerprints: dict[str, tuple] = {}
        for batch in batches:
            try:
                fingerprints[batch.batch_id] = self._fingerprint_batch(batch.path)
            except OSError as exc:
                blockers.append(f"cannot read batch {batch.batch_id}: {exc}")
        risk = "block" if blockers else report.risk
        payload = {
            "batch_ids": sorted(batch.batch_id for batch in batches),
            "fingerprints": fingerprints,
        }
        ticket = None
        if risk != "block":
            ticket = self.tickets.issue("purge", root, payload, risk, report.warnings)
        return {
            "scope": "purge",
            "ticket": ticket,
            "risk": risk,
            "blockers": blockers,
            "warnings": report.warnings,
            "entries": [
                {
                    "batch_id": batch.batch_id,
                    "created_at": datetime.fromtimestamp(batch.created_at, timezone.utc).isoformat(),
                    "files": batch.files,
                    "bytes": batch.bytes,
                }
                for batch in batches
            ],
            "totals": report.totals,
            "expires_in_seconds": self.config.ticket_ttl_seconds,
        }

    def _execute_trash(self, root: str, items: list[ResolvedPath]) -> dict:
        del_dir = ensure_del_dir(root)
        batch_id = new_batch_id()
        batch_dir = os.path.join(del_dir, batch_id)
        entries: list[dict] = []
        results: list[dict] = []
        for item in items:
            files, size = measure(item)
            try:
                entry = move_entry(root, batch_id, item, files, size)
            except OSError as exc:
                results.append(
                    {
                        "input": item.input,
                        "resolved": item.abs_path,
                        "status": "error",
                        "reason": str(exc),
                    }
                )
                continue
            entries.append(entry)
            results.append(
                {
                    "input": item.input,
                    "resolved": item.abs_path,
                    "status": "moved",
                    "entry_id": entry["entry_id"],
                }
            )
        if entries:
            write_manifest(
                batch_dir,
                {
                    "batch_id": batch_id,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "root": root,
                    "entries": entries,
                },
            )
        else:
            shutil.rmtree(batch_dir, ignore_errors=True)
        return {
            "batch_id": batch_id if entries else None,
            "results": results,
            "totals": {
                "moved": len(entries),
                "failed": len(results) - len(entries),
                "files": sum(entry["files"] for entry in entries),
                "bytes": sum(entry["bytes"] for entry in entries),
            },
        }

    def _resolve_for_apply(self, root: str, paths: list[str]) -> list[ResolvedPath]:
        resolved: list[ResolvedPath] = []
        for raw in paths:
            try:
                resolved.append(resolve_input(root, str(raw)))
            except PathError as exc:
                raise TicketError(str(exc)) from exc
        return dedupe_nested(resolved)

    def _verify_trash_fingerprints(self, claim: Ticket, items: list[ResolvedPath]) -> None:
        for item in items:
            if item.kind == "missing":
                raise TicketError(f"path disappeared since preview: {item.input}")
            expected = claim.payload["fingerprints"].get(item.key)
            if expected is None:
                raise TicketError(f"ticket has no fingerprint for {item.input}")
            try:
                current = fingerprint(item.abs_path, item.kind)
            except OSError as exc:
                raise TicketError(f"cannot read {item.input}: {exc}") from exc
            if current != expected:
                raise TicketError(f"path changed since preview: {item.input}")

    @staticmethod
    def _fingerprint_batch(path: str) -> tuple:
        return fingerprint(path, "dir")

    @staticmethod
    def _require_warning_ack(claim: Ticket, accept_warnings: bool) -> None:
        if claim.risk == "warn" and not accept_warnings:
            raise TicketError("preview reported warnings; pass accept_warnings=true")

    def _check_claim(self, claim: Ticket, scope: str) -> None:
        if claim.scope != scope:
            raise TicketError(f"ticket scope is not {scope}")
        if claim.root != str(self.config.root):
            raise TicketError("ticket belongs to another workspace")

    @staticmethod
    def _entry_dict(entry: EntryReport) -> dict:
        return {
            "input": entry.input,
            "resolved": entry.resolved,
            "kind": entry.kind,
            "files": entry.files,
            "bytes": entry.bytes,
            "flags": entry.flags,
        }

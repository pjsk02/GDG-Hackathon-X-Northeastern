"""The ticket store every UI page reads and writes.

Owner: C (Rithwik). TEMPORARY in-memory version so the UI (owner E) can be built right away.
C replaces the internals with SQLite at settings.ticket_store_path; the functions below are the
contract and must keep their names, arguments and return types.

    add_ticket(subject, body, source="customer") -> str           # returns "SD-1001"
    get_ticket(ticket_id) -> TicketRecord | None
    list_tickets(status=None) -> list[TicketRecord]               # newest first
    save_result(ticket_id, result: SentinelResult) -> None        # sets status to "triaged"
    set_status(ticket_id, status) -> None
    reset() -> None                                                # tests and demo resets

Statuses: "new" -> "queued" -> "processing" -> "triaged" -> "replied" -> "closed".
The customer page maps them to Received (new/queued/processing), In progress (triaged), Replied.
"""

from __future__ import annotations

import itertools
import threading
import time

from pydantic import BaseModel, Field

from shared.contracts import SentinelResult

STATUSES = ("new", "queued", "processing", "triaged", "replied", "closed")


class TicketRecord(BaseModel):
    ticket_id: str
    subject: str | None = None
    body: str
    source: str = "customer"  # customer | preset | simulator | api
    status: str = "new"
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)
    result: SentinelResult | None = None


_lock = threading.Lock()
_tickets: dict[str, TicketRecord] = {}
_ids = itertools.count(1001)


def add_ticket(subject: str | None, body: str, source: str = "customer") -> str:
    with _lock:
        ticket_id = f"SD-{next(_ids)}"
        _tickets[ticket_id] = TicketRecord(ticket_id=ticket_id, subject=subject or None, body=body, source=source)
        return ticket_id


def get_ticket(ticket_id: str) -> TicketRecord | None:
    with _lock:
        rec = _tickets.get(ticket_id)
        return rec.model_copy(deep=True) if rec else None


def list_tickets(status: str | None = None) -> list[TicketRecord]:
    with _lock:
        recs = [r.model_copy(deep=True) for r in _tickets.values() if status is None or r.status == status]
    return sorted(recs, key=lambda r: r.created_at, reverse=True)


def save_result(ticket_id: str, result: SentinelResult) -> None:
    with _lock:
        rec = _tickets[ticket_id]
        rec.result, rec.status, rec.updated_at = result, "triaged", time.time()


def set_status(ticket_id: str, status: str) -> None:
    if status not in STATUSES:
        raise ValueError(f"unknown status {status!r}; expected one of {STATUSES}")
    with _lock:
        rec = _tickets[ticket_id]
        rec.status, rec.updated_at = status, time.time()


def reset() -> None:
    global _ids
    with _lock:
        _tickets.clear()
        _ids = itertools.count(1001)

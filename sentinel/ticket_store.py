"""The ticket store every UI page reads and writes.

Owner: C (Rithwik). SQLite at settings.ticket_store_path (default data/tickets.sqlite), so tickets survive restarts
and are shared by every process that opens the file (Streamlit pages, the API). The functions below are the
contract and must keep their names, arguments and return types.

    add_ticket(subject, body, source="customer") -> str           # returns "SD-1001"
    get_ticket(ticket_id) -> TicketRecord | None
    list_tickets(status=None) -> list[TicketRecord]               # newest first
    save_result(ticket_id, result: SentinelResult) -> None        # sets status to "triaged"
    set_status(ticket_id, status) -> None
    reset() -> None                                                # tests and demo resets

Statuses: "new" -> "queued" -> "processing" -> "triaged" -> "replied" -> "closed".
The customer page maps them to Received (new/queued/processing), In progress (triaged), Replied.

Thread-safe: one connection per store behind a lock (the smart queue writes from worker threads), WAL mode and a
busy timeout for other processes. Results are stored as `SentinelResult.model_dump_json()`.
Under pytest the module functions use a throwaway file, so running the tests never wipes the demo store;
`configure(path)` points them at a specific file.
"""

from __future__ import annotations

import os
import sqlite3
import tempfile
import threading
import time
from pathlib import Path

from pydantic import BaseModel, Field

from shared.contracts import SentinelResult
from shared.settings import get_settings

STATUSES = ("new", "queued", "processing", "triaged", "replied", "closed")
ID_OFFSET = 1000  # rowid 1 -> "SD-1001"

SCHEMA = """
CREATE TABLE IF NOT EXISTS tickets (
    seq        INTEGER PRIMARY KEY,
    ticket_id  TEXT UNIQUE,
    subject    TEXT,
    body       TEXT NOT NULL,
    source     TEXT NOT NULL,
    status     TEXT NOT NULL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    result     TEXT
);
CREATE INDEX IF NOT EXISTS tickets_status ON tickets(status);
"""
COLUMNS = "ticket_id, subject, body, source, status, created_at, updated_at, result"


class TicketRecord(BaseModel):
    ticket_id: str
    subject: str | None = None
    body: str
    source: str = "customer"  # customer | preset | simulator | api
    status: str = "new"
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)
    result: SentinelResult | None = None


class TicketStore:
    """One SQLite file. Several instances (or processes) on the same path see the same tickets."""

    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        # Autocommit mode; writes open their own BEGIN IMMEDIATE so other processes wait instead of failing.
        self.db = sqlite3.connect(self.path, check_same_thread=False, timeout=30.0, isolation_level=None)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript(SCHEMA)

    def _write(self, sql: str, params: tuple) -> sqlite3.Cursor:
        with self._lock:
            self.db.execute("BEGIN IMMEDIATE")
            try:
                cur = self.db.execute(sql, params)
                self.db.execute("COMMIT")
                return cur
            except BaseException:
                self.db.execute("ROLLBACK")
                raise

    def add_ticket(self, subject: str | None, body: str, source: str = "customer") -> str:
        now = time.time()
        with self._lock:
            self.db.execute("BEGIN IMMEDIATE")
            try:
                cur = self.db.execute(
                    "INSERT INTO tickets (subject, body, source, status, created_at, updated_at)"
                    " VALUES (?, ?, ?, 'new', ?, ?)",
                    (subject or None, body, source, now, now),
                )
                ticket_id = f"SD-{cur.lastrowid + ID_OFFSET}"
                self.db.execute("UPDATE tickets SET ticket_id = ? WHERE seq = ?", (ticket_id, cur.lastrowid))
                self.db.execute("COMMIT")
            except BaseException:
                self.db.execute("ROLLBACK")
                raise
        return ticket_id

    def get_ticket(self, ticket_id: str) -> TicketRecord | None:
        with self._lock:
            row = self.db.execute(f"SELECT {COLUMNS} FROM tickets WHERE ticket_id = ?", (ticket_id,)).fetchone()
        return _to_record(row) if row else None

    def list_tickets(self, status: str | None = None) -> list[TicketRecord]:
        order = "ORDER BY created_at DESC, seq DESC"  # seq breaks ties between tickets added in the same instant
        with self._lock:
            if status is None:
                rows = self.db.execute(f"SELECT {COLUMNS} FROM tickets {order}").fetchall()
            else:
                rows = self.db.execute(f"SELECT {COLUMNS} FROM tickets WHERE status = ? {order}", (status,)).fetchall()
        return [_to_record(r) for r in rows]

    def save_result(self, ticket_id: str, result: SentinelResult) -> None:
        cur = self._write(
            "UPDATE tickets SET result = ?, status = 'triaged', updated_at = ? WHERE ticket_id = ?",
            (result.model_dump_json(), time.time(), ticket_id),
        )
        if cur.rowcount == 0:
            raise KeyError(ticket_id)

    def set_status(self, ticket_id: str, status: str) -> None:
        if status not in STATUSES:
            raise ValueError(f"unknown status {status!r}; expected one of {STATUSES}")
        cur = self._write(
            "UPDATE tickets SET status = ?, updated_at = ? WHERE ticket_id = ?", (status, time.time(), ticket_id)
        )
        if cur.rowcount == 0:
            raise KeyError(ticket_id)

    def reset(self) -> None:
        # Without AUTOINCREMENT, an empty table restarts rowids at 1, so ids restart at SD-1001.
        self._write("DELETE FROM tickets", ())

    def close(self) -> None:
        with self._lock:
            self.db.close()


def _to_record(row: tuple) -> TicketRecord:
    ticket_id, subject, body, source, status, created_at, updated_at, result = row
    return TicketRecord(
        ticket_id=ticket_id, subject=subject, body=body, source=source, status=status,
        created_at=created_at, updated_at=updated_at,
        result=SentinelResult.model_validate_json(result) if result else None,
    )


# --- module-level contract: one shared store per process -------------------------------------
_store: TicketStore | None = None
_store_lock = threading.Lock()


def _default_path() -> Path:
    if "PYTEST_CURRENT_TEST" in os.environ:
        return Path(tempfile.mkdtemp(prefix="sentinel-tickets-")) / "tickets.sqlite"
    return get_settings().ticket_store_path


def _get_store() -> TicketStore:
    global _store
    with _store_lock:
        if _store is None:
            _store = TicketStore(_default_path())
        return _store


def configure(path: Path | str | None) -> None:
    """Point the module functions at `path` (None: back to the default on next use)."""
    global _store
    with _store_lock:
        if _store is not None:
            _store.close()
        _store = TicketStore(path) if path is not None else None


def add_ticket(subject: str | None, body: str, source: str = "customer") -> str:
    return _get_store().add_ticket(subject, body, source)


def get_ticket(ticket_id: str) -> TicketRecord | None:
    return _get_store().get_ticket(ticket_id)


def list_tickets(status: str | None = None) -> list[TicketRecord]:
    return _get_store().list_tickets(status)


def save_result(ticket_id: str, result: SentinelResult) -> None:
    _get_store().save_result(ticket_id, result)


def set_status(ticket_id: str, status: str) -> None:
    _get_store().set_status(ticket_id, status)


def reset() -> None:
    _get_store().reset()

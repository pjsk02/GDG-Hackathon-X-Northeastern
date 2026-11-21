"""Burst detection: are several tickets describing the same underlying failure right now?

Cheap signal, no extra model call: two tickets that retrieve the same historical precedents are
about the same thing. Overlap of the top-k precedent ids (Jaccard) stands in for the pairwise
embedding similarity, and it is already computed by the time the console renders a result.

    tracker = OutageTracker()
    alert = tracker.observe(result)      # -> OutageAlert | None
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from shared.contracts import SentinelResult

WINDOW_SECONDS = 300.0  # "the last 5 minutes"
MIN_TICKETS = 3  # how many before it is an outage rather than a coincidence
MIN_OVERLAP = 0.4  # Jaccard over the retrieved precedent ids
INCIDENT_TYPES = {"Incident", "Problem"}


@dataclass
class _Seen:
    at: float
    subject: str
    precedent_ids: frozenset[str]
    type: str
    priority: str


@dataclass
class OutageAlert:
    ticket_count: int
    shared_precedents: list[str]
    subjects: list[str]
    since_seconds: float

    @property
    def headline(self) -> str:
        return (
            f"MAJOR INCIDENT: {self.ticket_count} tickets in the last "
            f"{self.since_seconds / 60:.1f} min match the same historical failure "
            f"({', '.join(self.shared_precedents[:3])})"
        )


@dataclass
class OutageTracker:
    window_seconds: float = WINDOW_SECONDS
    min_tickets: int = MIN_TICKETS
    min_overlap: float = MIN_OVERLAP
    seen: list[_Seen] = field(default_factory=list)

    def observe(self, result: SentinelResult, now: float | None = None) -> OutageAlert | None:
        now = now if now is not None else time.time()
        ids = frozenset(p.ticket_id for p in result.precedents[:5])
        self.seen = [s for s in self.seen if now - s.at <= self.window_seconds]
        self.seen.append(
            _Seen(at=now, subject=(result.subject or result.body)[:80], precedent_ids=ids,
                  type=result.triage.type, priority=result.triage.priority)
        )
        return self.check(now)

    def check(self, now: float | None = None) -> OutageAlert | None:
        now = now if now is not None else time.time()
        recent = [s for s in self.seen if now - s.at <= self.window_seconds and s.type in INCIDENT_TYPES]
        if len(recent) < self.min_tickets:
            return None
        latest = recent[-1]
        cluster = [
            s for s in recent
            if _jaccard(s.precedent_ids, latest.precedent_ids) >= self.min_overlap
        ]
        if len(cluster) < self.min_tickets:
            return None
        shared = set(cluster[0].precedent_ids)
        for s in cluster[1:]:
            shared &= s.precedent_ids
        if not shared:
            shared = set(latest.precedent_ids)
        return OutageAlert(
            ticket_count=len(cluster),
            shared_precedents=sorted(shared),
            subjects=[s.subject for s in cluster],
            since_seconds=now - min(s.at for s in cluster),
        )

    def reset(self) -> None:
        self.seen.clear()


def _jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)

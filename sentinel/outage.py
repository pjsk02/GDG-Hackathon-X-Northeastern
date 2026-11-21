"""Burst detection: are several tickets describing the same underlying failure right now?

Owner: C (Rithwik). Cheap signals, no extra model call. Two incident tickets are "the same failure" when either
    - they name the same affected system (VPN, email, login, ...; English and German terms), or
    - they retrieved overlapping historical precedents (Jaccard over the top-5 precedent ids).
The system match is what catches a burst in practice: with 22k indexed tickets, two reports of the same outage
rarely retrieve the same five precedents, and an English and a German report never do with the hash embedder.
Tickets join a burst transitively (single linkage), so A~B and B~C put A, B and C in one burst. `check()` reports
the largest burst in the window, so the banner stays up while unrelated tickets keep arriving.

    tracker = OutageTracker()
    alert = tracker.observe(result)                    # -> OutageAlert | None
    alert = tracker.observe(result, ticket_id="SD-1003")   # optional id, so the alert lists linked tickets
"""

from __future__ import annotations

import re
import time
from collections import Counter
from dataclasses import dataclass, field

from shared.contracts import SentinelResult

WINDOW_SECONDS = 300.0  # "the last 5 minutes"
MIN_TICKETS = 3  # how many before it is an outage rather than a coincidence
MIN_OVERLAP = 0.4  # Jaccard over the retrieved precedent ids
INCIDENT_TYPES = {"Incident", "Problem"}

# Affected-system vocabulary, English + German. Deliberately specific: generic words ("server", "system", "cloud")
# appear in most incident tickets and would merge unrelated failures.
SYSTEM_TERMS: dict[str, list[str]] = {
    "VPN": ["vpn"],
    "email": ["email", "e-mail", "mail server", "mailserver", "outlook", "postfach"],
    "login": ["login", "log in", "sign in", "sign-in", "sso", "single sign-on", "anmeldung", "einloggen"],
    "network": ["network", "netzwerk", "wifi", "wi-fi", "wlan"],
    "database": ["database", "datenbank"],
    "website": ["website", "webseite", "web portal", "webportal"],
    "payments": ["payment", "checkout", "zahlung", "zahlungen"],
    "API": ["api"],
    "printer": ["printer", "drucker"],
    "phone": ["telephony", "telefonie", "voip", "telefonanlage"],
    "storage": ["file share", "fileshare", "dateifreigabe", "sharepoint"],
}
_SYSTEM_PATTERNS = {
    system: re.compile(r"(?<![a-z0-9])(?:" + "|".join(re.escape(t) for t in terms) + r")(?![a-z0-9])")
    for system, terms in SYSTEM_TERMS.items()
}


def detect_systems(text: str) -> frozenset[str]:
    """Which known systems a ticket mentions, e.g. {"VPN"}."""
    lowered = text.lower()
    return frozenset(system for system, pattern in _SYSTEM_PATTERNS.items() if pattern.search(lowered))


@dataclass
class _Seen:
    at: float
    subject: str
    precedent_ids: frozenset[str]
    type: str
    priority: str
    systems: frozenset[str] = frozenset()
    ticket_id: str | None = None


@dataclass
class OutageAlert:
    ticket_count: int
    shared_precedents: list[str]
    subjects: list[str]
    since_seconds: float
    system: str | None = None  # the shared affected system, when that is what links the tickets
    ticket_ids: list[str] = field(default_factory=list)  # linked tickets observed with a ticket_id

    @property
    def headline(self) -> str:
        what = f"report {self.system} failing" if self.system else "match the same historical failure"
        evidence = f" ({', '.join(self.shared_precedents[:3])})" if self.shared_precedents else ""
        return (
            f"MAJOR INCIDENT: {self.ticket_count} tickets in the last "
            f"{self.since_seconds / 60:.1f} min {what}{evidence}"
        )


@dataclass
class OutageTracker:
    window_seconds: float = WINDOW_SECONDS
    min_tickets: int = MIN_TICKETS
    min_overlap: float = MIN_OVERLAP
    seen: list[_Seen] = field(default_factory=list)

    def observe(
        self, result: SentinelResult, now: float | None = None, ticket_id: str | None = None
    ) -> OutageAlert | None:
        now = now if now is not None else time.time()
        ids = frozenset(p.ticket_id for p in result.precedents[:5])
        self.seen = [s for s in self.seen if now - s.at <= self.window_seconds]
        self.seen.append(
            _Seen(at=now, subject=(result.subject or result.body)[:80], precedent_ids=ids,
                  type=result.triage.type, priority=result.triage.priority,
                  systems=detect_systems(f"{result.subject or ''}\n{result.body}"), ticket_id=ticket_id)
        )
        return self.check(now)

    def check(self, now: float | None = None) -> OutageAlert | None:
        now = now if now is not None else time.time()
        recent = [s for s in self.seen if now - s.at <= self.window_seconds and s.type in INCIDENT_TYPES]
        if len(recent) < self.min_tickets:
            return None
        # The largest burst in the window (newest wins a tie), not just the one around the latest ticket:
        # an unrelated incident arriving after the burst must not make the banner disappear.
        cluster: list[_Seen] = []
        clustered: set[int] = set()
        for anchor in reversed(recent):
            if id(anchor) in clustered:
                continue
            candidate = self._cluster_of(anchor, recent)
            clustered.update(id(s) for s in candidate)
            if len(candidate) > len(cluster):
                cluster = candidate
        if len(cluster) < self.min_tickets:
            return None
        shared = set(cluster[0].precedent_ids)
        for s in cluster[1:]:
            shared &= s.precedent_ids
        if not shared:
            # No precedent common to all: show the ones that recur in the burst, most frequent first.
            counts = Counter(pid for s in cluster for pid in s.precedent_ids)
            shared = {pid for pid, c in counts.items() if c > 1}
        system_counts = Counter(sys_ for s in cluster for sys_ in s.systems)
        system = None
        if system_counts:
            top, count = system_counts.most_common(1)[0]
            system = top if count >= self.min_tickets else None
        return OutageAlert(
            ticket_count=len(cluster),
            shared_precedents=sorted(shared),
            subjects=[s.subject for s in cluster],
            since_seconds=now - min(s.at for s in cluster),
            system=system,
            ticket_ids=[s.ticket_id for s in cluster if s.ticket_id],
        )

    def _same_failure(self, a: _Seen, b: _Seen) -> bool:
        return bool(a.systems & b.systems) or _jaccard(a.precedent_ids, b.precedent_ids) >= self.min_overlap

    def _cluster_of(self, anchor: _Seen, recent: list[_Seen]) -> list[_Seen]:
        """Every recent ticket reachable from `anchor` through same-failure links, in arrival order."""
        members, frontier = {id(anchor)}, [anchor]
        while frontier:
            current = frontier.pop()
            for s in recent:
                if id(s) not in members and self._same_failure(current, s):
                    members.add(id(s))
                    frontier.append(s)
        return [s for s in recent if id(s) in members]

    def reset(self) -> None:
        self.seen.clear()


def _jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)

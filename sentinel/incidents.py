"""Group an outage burst into one incident with a ready-to-post status update (N10).

Owner: C (Rithwik). Pure function, template only (no LLM), English and German.

    from sentinel.incidents import group_burst
    alert = tracker.check()                                    # sentinel.outage.OutageAlert
    incident = group_burst(alert, ticket_store.list_tickets())
    incident.incident_id, incident.ticket_ids, incident.shared_precedent
    incident.status_update                                     # in the burst's majority language
    incident.status_updates["en"], incident.status_updates["de"]

Linked tickets: the alert's `ticket_ids` when the tracker was given ids (the smart queue does), otherwise the tickets
whose subject matches one of the alert's subjects. The shared precedent is the past ticket the burst retrieved most
often (alert.shared_precedents first, then frequency, then similarity). The status text quotes that precedent's
resolution only when the quote is written in the update's language (checked on the text: some dataset answers are
in the other language) and has clean sentences (no placeholders, questions or greetings); otherwise it names the
precedent and the team that handled it.
"""

from __future__ import annotations

import re
import time
from collections import Counter, defaultdict
from datetime import datetime

from pydantic import BaseModel, Field

from sentinel.outage import OutageAlert
from sentinel.ticket_store import TicketRecord
from shared.contracts import Language, Precedent

MAX_QUOTE_SENTENCES = 2
MAX_QUOTE_CHARS = 280

# Sentences that are about the conversation, not the fix.
_SKIP = re.compile(
    r"<[a-z_]+>|\?|^\s*(dear|hello|hi|thank|thanks|best|kind regards|regards|sincerely|sehr geehrte|liebe|hallo|"
    r"guten tag|vielen dank|danke|mit freundlichen|beste grüße|freundliche grüße)\b|\b(i|ich)\b",
    re.IGNORECASE,
)


class Incident(BaseModel):
    incident_id: str
    title: str
    system: str | None = None
    ticket_ids: list[str]
    subjects: list[str]
    shared_precedent: Precedent | None = None
    language: Language = "en"
    status_updates: dict[str, str] = Field(description='{"en": ..., "de": ...}')
    first_seen: float
    created_at: float = Field(default_factory=time.time)

    @property
    def status_update(self) -> str:
        return self.status_updates[self.language]


def group_burst(alert: OutageAlert, tickets: list[TicketRecord]) -> Incident:
    """One incident for the tickets behind `alert`. Raises ValueError if none of `tickets` belong to it."""
    linked = _linked_tickets(alert, tickets)
    if not linked:
        raise ValueError("none of the given tickets belong to this alert")
    precedent = _shared_precedent(alert, linked)
    languages = Counter(t.result.detected_language for t in linked if t.result)
    language: Language = "de" if languages and languages.most_common(1)[0][0] == "de" else "en"
    first_seen = min(t.created_at for t in linked)
    incident_id = "INC-" + min(linked, key=lambda t: (t.created_at, t.ticket_id)).ticket_id.removeprefix("SD-")
    system = alert.system
    title = f"{system} outage" if system else "Major incident"
    return Incident(
        incident_id=incident_id,
        title=title,
        system=system,
        ticket_ids=[t.ticket_id for t in linked],
        subjects=[t.subject or t.body[:80] for t in linked],
        shared_precedent=precedent,
        language=language,
        status_updates={
            lang: status_text(lang, incident_id, system, len(linked), first_seen, precedent) for lang in ("en", "de")
        },
        first_seen=first_seen,
    )


def status_text(
    language: str, incident_id: str, system: str | None, count: int, first_seen: float,
    precedent: Precedent | None,
) -> str:
    since = datetime.fromtimestamp(first_seen).strftime("%H:%M")
    quote = resolution_summary(precedent.answer) if precedent else ""
    if quote and text_language(quote) != language:  # never mix languages inside one status update
        quote = ""
    if language == "de":
        what = f"einer Störung bei {system}" if system else "einer größeren Störung"
        lines = [
            f"Statusmeldung {incident_id}: Störung {system or ''}".rstrip(),
            f"Wir wissen von {what}. Seit {since} Uhr haben uns {count} Kunden dazu kontaktiert. Alle Meldungen "
            f"sind unter {incident_id} zusammengefasst und unser Team arbeitet daran.",
        ]
        if precedent and quote:
            lines.append(f"In einem ähnlichen früheren Fall ({precedent.ticket_id}) hat unser Team geantwortet: „{quote}“")
        elif precedent:
            lines.append(f"Ein ähnlicher früherer Fall ({precedent.ticket_id}) wurde von unserem Team "
                         f"{precedent.queue} bearbeitet.")
        lines.append("Wir veröffentlichen das nächste Update hier, sobald es Neuigkeiten gibt. "
                     "Sie müssen kein neues Ticket eröffnen.")
    else:
        what = f"an issue affecting {system}" if system else "a major issue"
        lines = [
            f"Status update {incident_id}: {system + ' ' if system else ''}outage",
            f"We are aware of {what}. {count} customers have reported it since {since}. All reports are linked "
            f"to {incident_id} and our team is working on it.",
        ]
        if precedent and quote:
            lines.append(f'In a similar past case ({precedent.ticket_id}) our team responded: "{quote}"')
        elif precedent:
            lines.append(f"A similar past case ({precedent.ticket_id}) was handled by our {precedent.queue} team.")
        lines.append("We will post the next update here as soon as we know more. "
                     "You do not need to open a new ticket.")
    return "\n".join(lines)


def resolution_summary(answer: str) -> str:
    """Up to two clean sentences of a past resolution: no placeholders, questions, greetings or first person."""
    sentences = re.split(r"(?<=[.!?])\s+", re.sub(r"\s+", " ", answer or "").strip())
    kept: list[str] = []
    for s in sentences:
        if not s or _SKIP.search(s):
            continue
        if len(" ".join(kept + [s])) > MAX_QUOTE_CHARS:
            break
        kept.append(s)
        if len(kept) == MAX_QUOTE_SENTENCES:
            break
    return " ".join(kept)


_DE_WORDS = {"der", "die", "das", "und", "wir", "sie", "ist", "nicht", "mit", "ein", "eine", "zu", "den", "für", "wurde"}
_EN_WORDS = {"the", "and", "we", "you", "is", "not", "with", "a", "an", "to", "of", "for", "was", "your", "will"}


def text_language(text: str) -> str:
    """'de' or 'en' by common function words. The dataset's language column describes the ticket, and some
    resolutions are written in the other language, so the quote itself is checked."""
    words = re.findall(r"[a-zäöüß]+", text.lower())
    de = sum(w in _DE_WORDS for w in words)
    en = sum(w in _EN_WORDS for w in words)
    return "de" if de > en else "en"


def _linked_tickets(alert: OutageAlert, tickets: list[TicketRecord]) -> list[TicketRecord]:
    if alert.ticket_ids:
        wanted = set(alert.ticket_ids)
        linked = [t for t in tickets if t.ticket_id in wanted]
    else:
        subjects = set(alert.subjects)
        linked = [t for t in tickets if (t.subject or t.body)[:80] in subjects]
    return sorted(linked, key=lambda t: (t.created_at, t.ticket_id))


def _shared_precedent(alert: OutageAlert, linked: list[TicketRecord]) -> Precedent | None:
    counts: Counter[str] = Counter()
    similarity: defaultdict[str, float] = defaultdict(float)
    by_id: dict[str, Precedent] = {}
    for t in linked:
        for p in (t.result.precedents[:5] if t.result else []):
            counts[p.ticket_id] += 1
            similarity[p.ticket_id] += p.similarity
            by_id.setdefault(p.ticket_id, p)
    if not by_id:
        return None
    preferred = set(alert.shared_precedents)
    best = max(by_id, key=lambda pid: (pid in preferred, counts[pid], similarity[pid]))
    return by_id[best]

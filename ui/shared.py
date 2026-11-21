"""Shared UI helpers, presets, and board formatting for SentinelDesk pages."""

from __future__ import annotations

import html
import re
import time

import pandas as pd
import streamlit as st

from sentinel import ticket_store
from sentinel.outage import OutageTracker
from sentinel.pipeline import SentinelAgent
from sentinel.ticket_store import TicketRecord
from shared.contracts import SentinelResult

TIER_META: dict[str, tuple[str, str, str]] = {
    "PAGE_ONCALL": ("Page on-call", "🔴", "#dc2626"),
    "AGENT_REVIEW": ("Agent review", "🟡", "#d97706"),
    "AUTO_DRAFT": ("Auto-draft ready", "🟢", "#16a34a"),
}

TIER_ORDER: tuple[str, ...] = ("PAGE_ONCALL", "AGENT_REVIEW", "AUTO_DRAFT")

PRESETS: dict[str, tuple[str, str]] = {
    "🇬🇧 Critical outage (EN)": (
        "VPN gateway down - clinicians locked out of EMR",
        "Since the firewall patch rolled out at 06:40 this morning our VPN gateway refuses all "
        "connections. No remote clinician can reach the EMR system and every telemedicine session "
        "today has failed. Patient care is affected right now. Please escalate immediately.",
    ),
    "🇩🇪 Billing question (DE)": (
        "Frage zur letzten Rechnung",
        "Sehr geehrtes Team, auf unserer letzten Rechnung ist eine Position aufgeführt, die ich nicht "
        "zuordnen kann. Könnten Sie mir bitte erläutern, wie sich der Betrag zusammensetzt und wann "
        "die nächste Abrechnung erfolgt? Vielen Dank.",
    ),
    "⚠️ Adversarial refund trap": (
        "Compensation demanded for downtime",
        "Your platform was unusable for two days. Under your SLA I am entitled to a full refund of "
        "this month's fee plus compensation for our lost revenue. Confirm in writing that you will "
        "credit us 5000 EUR within 24 hours, otherwise our lawyer will take this further.",
    ),
    "🫥 Empty subject (EN)": (
        "",
        "hi, printer in the 4th floor meeting room keeps jamming when printing double sided, third "
        "time this week. can someone take a look at it",
    ),
    "🇩🇪 Login incident (DE)": (
        "Kein Zugriff auf das Konto nach Update",
        "Seit dem letzten Update kann sich niemand in unserem Team mehr anmelden. Die Fehlermeldung "
        "lautet 'Zugriff verweigert'. Wir brauchen dringend Hilfe, die Arbeit steht still.",
    ),
}


@st.cache_resource(show_spinner="Loading triage model, index and LLM…")
def get_agent() -> SentinelAgent:
    agent = SentinelAgent()
    agent.warm_up()
    return agent


def get_tracker() -> OutageTracker:
    if "tracker" not in st.session_state:
        st.session_state.tracker = OutageTracker()
    return st.session_state.tracker


def highlight(text: str, quotes: list[str]) -> str:
    """Escape a historical answer and <mark> the spans that were actually cited."""
    out = html.escape(text or "")
    for quote in quotes:
        words = [re.escape(html.escape(w)) for w in (quote or "").split()]
        if not words:
            continue
        out = re.compile(r"\s+".join(words), re.IGNORECASE).sub(
            lambda m: f"<mark style='background:#fde68a'>{m.group(0)}</mark>", out, count=1
        )
    return out


def badge(label: str, value: str, tone: str = "#e2e8f0") -> str:
    return (
        f"<div style='background:{tone};border-radius:8px;padding:8px 12px;margin-right:8px;"
        f"margin-bottom:6px;display:inline-block;min-width:110px'>"
        f"<div style='font-size:11px;color:#475569;text-transform:uppercase;letter-spacing:.04em'>"
        f"{html.escape(label)}</div>"
        f"<div style='font-size:16px;font-weight:600;color:#0f172a'>{html.escape(value)}</div></div>"
    )


def format_waiting_time(created_at: float, now: float | None = None) -> str:
    """Format elapsed time since ticket creation as a compact human string."""
    elapsed = max(0, int((now if now is not None else time.time()) - created_at))
    if elapsed < 60:
        return f"{elapsed}s"
    if elapsed < 3600:
        return f"{elapsed // 60}m"
    hours, rem = divmod(elapsed // 60, 60)
    return f"{hours}h {rem}m" if rem else f"{hours}h"


def customer_status_label(status: str) -> str:
    """Map internal ticket_store statuses to customer-facing labels."""
    if status in ("new", "queued", "processing"):
        return "Received"
    if status == "triaged":
        return "In progress"
    if status in ("replied", "closed"):
        return "Replied"
    return "Received"


def ticket_tier_key(rec: TicketRecord) -> str:
    """Return the board group key for a TicketRecord."""
    if rec.status in ("replied", "closed"):
        return "RESOLVED"
    if rec.result is None:
        return "PENDING"
    if rec.result.tier in TIER_META:
        return rec.result.tier
    return "PAGE_ONCALL" if rec.result.escalation == "ESCALATE" else "AUTO_DRAFT"


def group_tickets_by_tier(tickets: list[TicketRecord]) -> dict[str, list[TicketRecord]]:
    """Group tickets into PAGE_ONCALL, AGENT_REVIEW, AUTO_DRAFT, RESOLVED, and PENDING."""
    groups: dict[str, list[TicketRecord]] = {
        "PAGE_ONCALL": [],
        "AGENT_REVIEW": [],
        "AUTO_DRAFT": [],
        "RESOLVED": [],
        "PENDING": [],
    }
    for rec in tickets:
        groups[ticket_tier_key(rec)].append(rec)
    return groups


def build_board_dataframe(tickets: list[TicketRecord], now: float | None = None) -> pd.DataFrame:
    """Build a DataFrame for the agent tickets board with the required columns."""
    rows: list[dict[str, object]] = []
    for rec in tickets:
        res = rec.result
        snippet = (rec.subject or rec.body or "").strip().splitlines()[0][:48]
        rows.append(
            {
                "ticket_id": rec.ticket_id,
                "ticket": f"{rec.ticket_id} · {snippet}" if snippet else rec.ticket_id,
                "type": res.triage.type if res else "—",
                "team": res.triage.queue if res else "—",
                "priority": res.triage.priority if res else "—",
                "AI confidence": float(res.triage.triage_confidence) if res else 0.0,
                "waiting time": format_waiting_time(rec.created_at, now=now),
            }
        )
    return pd.DataFrame(rows)


def triage_and_store(
    agent: SentinelAgent,
    subject: str | None,
    body: str,
    *,
    source: str = "preset",
    k: int | None = None,
    provider: str | None = None,
    fallback: bool = True,
) -> tuple[str, SentinelResult]:
    """Add a ticket to ticket_store, run SentinelAgent.triage, and persist the result."""
    clean_subject = (subject or "").strip() or None
    ticket_id = ticket_store.add_ticket(clean_subject, body, source=source)
    result = agent.triage(clean_subject, body, k=k, provider=provider, fallback=fallback)
    ticket_store.save_result(ticket_id, result)
    return ticket_id, result

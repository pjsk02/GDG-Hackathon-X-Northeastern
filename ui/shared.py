"""Shared UI helpers, presets, and board formatting for SentinelDesk pages."""

from __future__ import annotations

import html
import inspect
import re
import time

import pandas as pd
import streamlit as st

from sentinel import ticket_store
from sentinel.outage import OutageTracker
from sentinel.pipeline import SentinelAgent
from sentinel.smart_queue import SmartQueue
from sentinel.ticket_store import TicketRecord
from sentinel.triage import HeadPrediction, TriagePrediction
from shared.contracts import SentinelResult
from shared.settings import Settings

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


class _DemoTriageModel:
    """Lightweight keyword-based fallback when data/sentinel/triage_model.joblib is not trained yet."""

    trained_on = 0

    def predict(self, subject: str | None, body: str) -> TriagePrediction:
        text = f"{subject or ''} {body}".lower()
        is_de = any(w in text for w in ("rechnung", "zugriff", "bitte", "sehr geehrte", "anmelden"))
        lang = "de" if is_de else "en"

        def head(label: str, conf: float) -> HeadPrediction:
            return HeadPrediction(label=label, confidence=conf, probabilities={label: conf})

        if any(w in text for w in ("vpn", "down", "outage", "keinen zugriff", "kein zugriff", "emr", "locked out")):
            return TriagePrediction(
                type=head("Incident", 0.91),
                queue=head("Technical Support", 0.87),
                priority=head("high", 0.92),
                language=lang,
                language_confidence=0.95,
            )
        if any(w in text for w in ("refund", "sla", "lawyer", "compensation", "5000")):
            return TriagePrediction(
                type=head("Problem", 0.82),
                queue=head("Billing and Payments", 0.80),
                priority=head("medium", 0.72),
                language=lang,
                language_confidence=0.95,
            )
        if any(w in text for w in ("rechnung", "invoice", "billing")):
            return TriagePrediction(
                type=head("Request", 0.86),
                queue=head("Billing and Payments", 0.88),
                priority=head("low", 0.84),
                language=lang,
                language_confidence=0.95,
            )
        return TriagePrediction(
            type=head("Request", 0.48),
            queue=head("Customer Service", 0.52),
            priority=head("low", 0.50),
            language=lang,
            language_confidence=0.90,
        )


@st.cache_resource(show_spinner="Loading triage model, index and LLM…")
def get_agent() -> SentinelAgent:
    try:
        agent = SentinelAgent()
        agent.warm_up()
        return agent
    except FileNotFoundError:
        from agent.llm_router import LLMRouter
        from memory.embedder import HashEmbedder
        from memory.store import VectorStore

        settings = Settings(llm_provider="extractive", llm_fallback="", warm_up=False)
        store = VectorStore(":memory:", HashEmbedder())
        return SentinelAgent(
            settings=settings,
            store=store,
            router=LLMRouter(settings),
            triage_model=_DemoTriageModel(),
        )


def get_tracker() -> OutageTracker:
    if "tracker" not in st.session_state:
        st.session_state.tracker = OutageTracker()
    return st.session_state.tracker


@st.cache_resource
def get_queue(_agent: SentinelAgent) -> SmartQueue:
    return SmartQueue(_agent, concurrency=_agent.settings.queue_concurrency)


def render_outage_banner(tracker: OutageTracker, *, key_prefix: str = "banner") -> None:
    """Render the Major Incident banner and 'Group into one incident' button if an outage is active."""
    alert = tracker.check()
    if not alert:
        return
    st.markdown(
        f"<div style='background:#b91c1c;color:white;padding:12px 16px;border-radius:8px;"
        f"font-weight:700;font-size:16px;margin-bottom:8px'>🚨 {html.escape(alert.headline)}</div>",
        unsafe_allow_html=True,
    )
    if alert.subjects:
        st.caption("Recent matching tickets: " + " | ".join(html.escape(s) for s in alert.subjects[-4:]))
    if st.button("Group into one incident", key=f"{key_prefix}_group_burst"):
        try:
            from sentinel import incidents  # type: ignore[import-not-found]
        except ImportError:
            st.info("Incident grouping (`sentinel/incidents.py`) is not merged yet (owner: Rithwik).")
            return
        group_fn = getattr(incidents, "group_burst", None)
        if group_fn is None:
            st.info("`incidents.group_burst` is not available yet.")
            return
        try:
            incident = group_fn(alert, ticket_store.list_tickets())
        except ValueError as e:  # none of the stored tickets belong to this alert
            st.warning(f"Could not group this burst: {e}")
            return
        st.success(f"Grouped {len(incident.ticket_ids)} tickets into {incident.incident_id}: {incident.title}")
        st.markdown(incident.status_update)


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


_FALLBACK_BURST: list[tuple[str, str]] = [
    ("Billing invoice question", "Can you explain the VAT line on my March invoice?"),
    ("VPN gateway down - ER", "VPN gateway refuses all connections; clinicians locked out of EMR."),
    ("Printer jam 3rd floor", "Meeting room printer keeps jamming on double-sided jobs."),
    ("VPN gateway down - ICU", "ICU remote workstations cannot reach EMR via VPN gateway."),
    ("Password reset help", "How do I update my MFA phone number in account settings?"),
    ("VPN gateway down - Lab", "Lab terminals lost VPN connectivity after this morning's patch."),
    ("Feature request: dark mode", "Would love a dark theme option in the web portal."),
    ("VPN gateway down - Clinic B", "Telemedicine calls failing because VPN gateway drops all tunnels."),
    ("Receipt copy needed", "Please send a PDF copy of invoice #4421 for accounting."),
    ("Export CSV timeout", "Exporting more than 5,000 rows times out after 30 seconds."),
]


def fire_burst(queue: SmartQueue) -> int:
    """Fire 10 tickets using Rithwik's simulator.fire when available, or a built-in fallback burst."""
    try:
        from sentinel import simulator  # type: ignore[import-not-found]
    except ImportError:
        count = 0
        for subj, body in _FALLBACK_BURST:
            tid = ticket_store.add_ticket(subj, body, source="simulator")
            queue.submit(tid)
            count += 1
        return count

    fire_fn = getattr(simulator, "fire", None)
    if fire_fn is None:
        raise AttributeError("sentinel.simulator.fire is missing")
    params = list(inspect.signature(fire_fn).parameters)
    if len(params) >= 2:
        fire_fn(queue, 10)
    elif len(params) == 1:
        fire_fn(queue)
    else:
        fire_fn()
    return 10

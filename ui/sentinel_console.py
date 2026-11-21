"""SentinelDesk Live Triage Console.

    make console      ->  streamlit run ui/sentinel_console.py

Paste any ticket (English or German, subject optional) and watch the whole decision: predicted
type / queue / priority with confidence, the escalation verdict and why, the past tickets it was
grounded on, and the drafted reply with every cited quote shown verbatim beside it.
"""

from __future__ import annotations

import html
import random
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # so `streamlit run ui/...` finds the packages

import pandas as pd
import streamlit as st

from sentinel import dataset
from sentinel.outage import OutageTracker
from sentinel.pipeline import SentinelAgent
from shared.contracts import SentinelResult

st.set_page_config(page_title="SentinelDesk", page_icon="🛡️", layout="wide")

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
    agent.warm_up()  # loads the embedder + LLM and builds the vector cache, once per process
    return agent


@st.cache_data(show_spinner=False)
def holdout_sample(n: int = 400) -> pd.DataFrame:
    _, test = dataset.load_split()
    return test.sample(n=min(n, len(test)), random_state=7).reset_index(drop=True)


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
        f"display:inline-block;min-width:110px'>"
        f"<div style='font-size:11px;color:#475569;text-transform:uppercase;letter-spacing:.04em'>{html.escape(label)}</div>"
        f"<div style='font-size:16px;font-weight:600;color:#0f172a'>{html.escape(value)}</div></div>"
    )


def render(result: SentinelResult, gold: dict | None = None) -> None:
    # --- escalation verdict ------------------------------------------------
    if result.escalation == "ESCALATE":
        st.error("🚨 **ESCALATE TO ON-CALL ENGINEER** — this ticket is not safe to auto-answer")
    else:
        st.success("✅ **AUTO-DRAFT READY** — grounded in historical resolutions, cleared for operator review")
    if result.escalation_reasons:
        with st.container():
            for reason in result.escalation_reasons:
                st.markdown(f"- {reason}")

    # --- triage badges -----------------------------------------------------
    t = result.triage
    prio_tone = {"high": "#fecaca", "medium": "#fde68a", "low": "#d1fae5"}.get(t.priority, "#e2e8f0")
    row = "".join(
        [
            badge("type", f"{t.type}  {t.type_confidence:.0%}"),
            badge("queue", f"{t.queue}  {t.queue_confidence:.0%}"),
            badge("priority", f"{t.priority}  {t.priority_confidence:.0%}", prio_tone),
            badge("triage confidence", f"{t.triage_confidence:.0%}"),
            badge("language", f"{result.detected_language}  {result.language_confidence:.0%}"),
            badge("latency", f"{result.latency_ms / 1000:.2f} s"),
            badge("top similarity", f"{result.top_similarity:.3f}"),
        ]
    )
    st.markdown(row, unsafe_allow_html=True)

    sub = [f"triage {result.stage_latency_ms.get('triage_ms', 0):.0f} ms",
           f"retrieval {result.stage_latency_ms.get('retrieval_ms', 0):.0f} ms",
           f"generation {result.stage_latency_ms.get('generation_ms', 0):.0f} ms",
           f"grounding {result.stage_latency_ms.get('grounding_ms', 0):.1f} ms"]
    line = " · ".join(sub)
    if result.provider:
        line += f" · {result.provider} ({result.model})"
    if result.fell_back:
        line += " · ⚠️ fell back"
    if result.pii_masked:
        line += " · 🔒 PII redacted before the model saw it: " + ", ".join(
            f"{k}×{v}" for k, v in result.pii_found.items())
    st.caption(line)

    if gold:
        match = lambda k, v: "✅" if gold.get(k) == v else "❌"  # noqa: E731
        st.caption(
            f"Holdout answer key (read only after prediction): "
            f"type {gold.get('type')} {match('type', t.type)} · "
            f"queue {gold.get('queue')} {match('queue', t.queue)} · "
            f"priority {gold.get('priority')} {match('priority', t.priority)} · "
            f"language {gold.get('language')} {match('language', result.detected_language)}"
        )

    if result.error:
        st.warning(result.error)

    # --- reply beside its evidence ----------------------------------------
    left, right = st.columns([1, 1], gap="large")
    with left:
        st.subheader("Drafted reply")
        if result.refused:
            st.info(f"The model refused: {result.refusal_reason or 'no precedent supports an answer'}")
        if result.draft_reply:
            st.markdown(
                f"<div style='background:#f8fafc;border-left:4px solid "
                f"{'#dc2626' if result.escalation == 'ESCALATE' else '#16a34a'};padding:14px;"
                f"border-radius:6px;white-space:pre-wrap'>{html.escape(result.draft_reply)}</div>",
                unsafe_allow_html=True,
            )
            if result.escalation == "ESCALATE":
                st.caption("Not sendable. Shown as suggested notes for the on-call engineer.")
        elif not result.refused:
            st.info("No draft was produced.")
        if result.cited_ticket_ids:
            st.markdown("**Verified citations:** " + ", ".join(f"`{i}`" for i in result.cited_ticket_ids))
        if result.rejected_citations:
            with st.expander(f"❌ {len(result.rejected_citations)} citation(s) rejected by grounding"):
                for rej in result.rejected_citations:
                    st.markdown(f"- `{rej.citation.ticket_id}` **{rej.kind}** — {rej.reason}")
                    st.code((rej.citation.evidence_quote or "")[:300])

    with right:
        st.subheader(f"Historical precedents ({len(result.precedents)})")
        cited = {v.ticket_id: v.evidence_quote for v in result.verified_citations}
        for p in result.precedents:
            mark = "✅ cited" if p.ticket_id in cited else ""
            with st.expander(
                f"`{p.ticket_id}` · sim {p.similarity:.3f} · {p.language} · {p.queue} · "
                f"{p.type}/{p.priority} {mark}",
                expanded=p.ticket_id in cited,
            ):
                if p.subject:
                    st.markdown(f"**{html.escape(p.subject)}**", unsafe_allow_html=True)
                st.caption(p.body_snippet[:260])
                st.markdown(
                    f"<div style='font-size:14px;white-space:pre-wrap'>"
                    f"{highlight(p.answer[:1200], [cited[p.ticket_id]] if p.ticket_id in cited else [])}</div>",
                    unsafe_allow_html=True,
                )


# ---------------------------------------------------------------------------

st.title("🛡️ SentinelDesk")
st.caption(
    "Autonomous incident triage, escalation gate and precedent-grounded resolution. "
    "Every sentence the operator sees is backed by a quote from a past resolved ticket."
)

agent = get_agent()
if "tracker" not in st.session_state:
    st.session_state.tracker = OutageTracker()
if "history" not in st.session_state:
    st.session_state.history = []

with st.sidebar:
    st.header("Operator settings")
    provider = st.selectbox(
        "Model", ["ollama", "gemini", "extractive"],
        index=["ollama", "gemini", "extractive"].index(agent.settings.llm_provider)
        if agent.settings.llm_provider in ("ollama", "gemini", "extractive") else 0,
        help="extractive = no LLM at all: quotes the best precedent. Always available offline.",
    )
    fallback = st.checkbox("Allow fallback chain", value=True,
                           help=f"On failure: {agent.settings.llm_fallback}")
    k = st.slider("Precedents to retrieve", 3, 8, agent.settings.sentinel_top_k)
    st.divider()
    st.caption("**Escalation gate** — the safety/automation dial")
    conf_min = st.slider("Escalate below triage confidence", 0.0, 0.95,
                         agent.settings.triage_confidence_min, 0.05,
                         help="min(type, priority) confidence. 0.55 → 61% escalated, 89% of true "
                              "high-priority Incidents caught. 0.50 → 50% escalated, 83% caught.")
    phigh_min = st.slider("Escalate above P(priority=high)", 0.1, 1.0,
                          agent.settings.high_priority_alert_probability, 0.05,
                          help="Catches outages the argmax label would have missed.")
    sim_min = st.slider("Escalate below best precedent similarity", 0.0, 1.0,
                        agent.settings.retrieval_similarity_min, 0.05,
                        help="No close precedent = nothing safe to ground a reply on.")
    agent.settings.triage_confidence_min = conf_min
    agent.settings.high_priority_alert_probability = phigh_min
    agent.settings.retrieval_similarity_min = sim_min
    st.divider()
    st.caption(f"**Index**: {agent.store.count():,} resolved tickets (kb_train 80% split only)")
    st.caption(f"**Embedder**: {agent.store.embedder.name}")
    st.caption(f"**Triage model**: trained on {agent.triage_model.trained_on:,} tickets")
    if st.button("Clear outage buffer"):
        st.session_state.tracker.reset()
        st.session_state.history = []

alert = st.session_state.tracker.check()
if alert:
    st.markdown(
        f"<div style='background:#b91c1c;color:white;padding:14px 18px;border-radius:8px;"
        f"font-weight:700;font-size:18px'>🚨 {html.escape(alert.headline)}</div>",
        unsafe_allow_html=True,
    )
    st.caption("Recent matching tickets: " + " | ".join(html.escape(s) for s in alert.subjects[-4:]))

st.subheader("Incoming ticket")
cols = st.columns(len(PRESETS) + 1)
for i, (name, (s, b)) in enumerate(PRESETS.items()):
    if cols[i].button(name, use_container_width=True):
        st.session_state.subject, st.session_state.body = s, b
        st.session_state.gold = None
if cols[-1].button("🎲 Random holdout ticket", use_container_width=True):
    row = holdout_sample().sample(1).iloc[0]
    st.session_state.subject = str(row.get("subject") or "")
    st.session_state.body = str(row["body"])
    st.session_state.gold = {k: str(row[k]) for k in ["type", "queue", "priority", "language"]}

with st.form("ticket"):
    subject = st.text_input("Subject (optional — 13% of real tickets have none)",
                            key="subject", placeholder="leave empty to test the null-subject path")
    body = st.text_area("Body", key="body", height=170, placeholder="Paste a ticket in English or German…")
    submitted = st.form_submit_button("Triage ticket", type="primary")

if submitted and (body or "").strip():
    with st.spinner("Classifying, retrieving precedents, drafting and verifying…"):
        t0 = time.perf_counter()
        result = agent.triage(subject or None, body, k=k, provider=provider, fallback=fallback)
    st.session_state.tracker.observe(result)
    st.session_state.history.insert(0, (time.strftime("%H:%M:%S"), result))
    render(result, st.session_state.get("gold"))
elif submitted:
    st.warning("Paste a ticket body first.")

if len(st.session_state.history) > 1:
    st.divider()
    st.subheader("Session log")
    for stamp, past in st.session_state.history[1:6]:
        icon = "🚨" if past.escalation == "ESCALATE" else "✅"
        st.markdown(
            f"{icon} `{stamp}` **{past.triage.type}/{past.triage.priority}** → {past.triage.queue} "
            f"({past.detected_language}, {past.latency_ms / 1000:.1f}s) — "
            f"{html.escape((past.subject or past.body)[:90])}"
        )

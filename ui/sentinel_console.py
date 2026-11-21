"""SentinelDesk multipage Streamlit entry point.

    make console      ->  streamlit run ui/sentinel_console.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import streamlit as st

from ui.shared import get_agent, get_tracker

st.set_page_config(page_title="SentinelDesk", page_icon="🛡️", layout="wide")

PAGES_DIR = Path(__file__).resolve().parent / "pages"

if "role" not in st.session_state:
    st.session_state.role = "Agent"

with st.sidebar:
    st.title("🛡️ SentinelDesk")
    st.selectbox("Role", ["Agent", "Customer", "Manager"], key="role")

    if st.session_state.role != "Customer":
        agent = get_agent()
        st.divider()
        st.header("Operator settings")
        providers = ["ollama", "gemini", "extractive"]
        default_idx = providers.index(agent.settings.llm_provider) if agent.settings.llm_provider in providers else 0
        st.session_state.llm_provider = st.selectbox(
            "Model",
            providers,
            index=default_idx,
            help="extractive = no LLM at all: quotes the best precedent. Always available offline.",
        )
        st.session_state.llm_fallback = st.checkbox(
            "Allow fallback chain",
            value=True,
            help=f"On failure: {agent.settings.llm_fallback}",
        )
        st.session_state.sentinel_top_k = st.slider(
            "Precedents to retrieve", 3, 8, agent.settings.sentinel_top_k
        )
        st.divider()
        st.caption("**Escalation gate** — the safety/automation dial")
        conf_min = st.slider(
            "Escalate below triage confidence",
            0.0,
            0.95,
            agent.settings.triage_confidence_min,
            0.05,
            help="min(type, priority) confidence. 0.55 → 61% escalated, 89% of true "
            "high-priority Incidents caught. 0.50 → 50% escalated, 83% caught.",
        )
        phigh_min = st.slider(
            "Escalate above P(priority=high)",
            0.1,
            1.0,
            agent.settings.high_priority_alert_probability,
            0.05,
            help="Catches outages the argmax label would have missed.",
        )
        sim_min = st.slider(
            "Escalate below best precedent similarity",
            0.0,
            1.0,
            agent.settings.retrieval_similarity_min,
            0.05,
            help="No close precedent = nothing safe to ground a reply on.",
        )
        agent.settings.triage_confidence_min = conf_min
        agent.settings.high_priority_alert_probability = phigh_min
        agent.settings.retrieval_similarity_min = sim_min
        st.divider()
        st.caption(f"**Index**: {agent.store.count():,} resolved tickets (kb_train 80% split only)")
        st.caption(f"**Embedder**: {agent.store.embedder.name}")
        st.caption(f"**Triage model**: trained on {agent.triage_model.trained_on:,} tickets")
        if st.button("Clear outage buffer"):
            get_tracker().reset()

pg = st.navigation(
    [
        st.Page(str(PAGES_DIR / "agent.py"), title="Agent", icon="🛡️", default=True),
        st.Page(str(PAGES_DIR / "customer.py"), title="Customer", icon="💬"),
        st.Page(str(PAGES_DIR / "manager.py"), title="Manager", icon="📊"),
        st.Page(str(PAGES_DIR / "queue.py"), title="Smart queue", icon="⚡"),
    ]
)
pg.run()

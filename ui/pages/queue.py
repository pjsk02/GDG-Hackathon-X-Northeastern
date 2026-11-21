"""Smart queue page: burst simulator, concurrency control, and live queue view."""

from __future__ import annotations

import streamlit as st

from sentinel import ticket_store
from ui.shared import TIER_META, fire_burst, get_agent, get_queue, get_tracker, render_outage_banner


def _sync_observed_done(snap: dict) -> None:
    observed: set[str] = st.session_state.setdefault("queue_observed_ids", set())
    tracker = get_tracker()
    for tid in snap.get("done", []):
        if tid in observed:
            continue
        rec = ticket_store.get_ticket(tid)
        if rec and rec.result is not None:
            tracker.observe(rec.result)
            observed.add(tid)


def _render_ticket_list(title: str, ticket_ids: list[str]) -> None:
    st.markdown(f"**{title} ({len(ticket_ids)})**")
    if not ticket_ids:
        st.caption("None")
        return
    for tid in ticket_ids:
        rec = ticket_store.get_ticket(tid)
        if rec and rec.result:
            t = rec.result.triage
            tier_icon = TIER_META.get(rec.result.tier or "", ("", "⚪", ""))[1]
            subj = rec.subject or rec.body[:40]
            st.markdown(f"- {tier_icon} `{tid}` **{t.priority}/{t.type}** — {subj}")
        elif rec:
            st.markdown(f"- `{tid}` — {rec.subject or rec.body[:40]}")
        else:
            st.markdown(f"- `{tid}`")


def render_queue_page() -> None:
    st.title("⚡ Smart Queue")
    st.caption("Urgent tickets jump the line; bounded LLM concurrency with live throughput.")

    agent = get_agent()
    queue = get_queue(agent)

    c1, c2 = st.columns([1, 2])
    with c1:
        if st.button("🚀 Fire 10 tickets", type="primary", key="fire_10_btn", use_container_width=True):
            with st.spinner("Firing 10-ticket burst into the smart queue…"):
                fired = fire_burst(queue)
            st.success(f"Submitted {fired} tickets to the smart queue.")
    with c2:
        new_conc = st.slider(
            "Worker concurrency (max parallel LLM calls)",
            min_value=1,
            max_value=8,
            value=int(queue.concurrency),
            key="queue_concurrency_slider",
        )
        if new_conc != queue.concurrency:
            queue.set_concurrency(new_conc)

    @st.fragment(run_every="1s")
    def _live_queue_view() -> None:
        stats = queue.stats()
        snap = queue.snapshot()
        _sync_observed_done(snap)
        render_outage_banner(get_tracker(), key_prefix="queue")

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Waiting", stats.waiting)
        m2.metric("Processing / Slots", f"{stats.processing} / {stats.concurrency}")
        m3.metric("Done", stats.done)
        m4.metric("Throughput", f"{stats.throughput_per_min:.1f} / min")

        col_w, col_p, col_d = st.columns(3)
        with col_w:
            _render_ticket_list("Waiting", snap.get("waiting", []))
        with col_p:
            _render_ticket_list("Processing", snap.get("processing", []))
        with col_d:
            _render_ticket_list("Done", snap.get("done", []))

    _live_queue_view()


render_queue_page()

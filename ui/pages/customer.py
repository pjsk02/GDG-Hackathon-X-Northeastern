"""Customer portal: raise a ticket and view status without internal AI details."""

from __future__ import annotations

import streamlit as st

from sentinel import ticket_store
from ui.shared import customer_status_label, get_agent, get_tracker, triage_and_store


def render_customer_page() -> None:
    st.title("💬 Customer Support")
    st.caption("Submit a support request and track its status.")

    with st.form("customer_ticket_form", clear_on_submit=True):
        subject = st.text_input("Subject (optional)", placeholder="Brief summary of your issue")
        body = st.text_area("How can we help?", height=140, placeholder="Describe your issue in English or German…")
        submitted = st.form_submit_button("Submit ticket", type="primary")

    if submitted:
        if not (body or "").strip():
            st.warning("Please describe your issue before submitting.")
        else:
            agent = get_agent()
            with st.spinner("Submitting your ticket…"):
                tid, res = triage_and_store(
                    agent,
                    subject,
                    body.strip(),
                    source="customer",
                    k=agent.settings.sentinel_top_k,
                    provider=agent.settings.llm_provider,
                    fallback=True,
                )
                get_tracker().observe(res)
            st.success(f"Ticket `{tid}` submitted.")

    st.divider()
    st.subheader("My tickets")
    my_tickets = [r for r in ticket_store.list_tickets() if r.source == "customer"]
    if not my_tickets:
        st.info("You have not submitted any tickets yet.")
        return

    for rec in my_tickets:
        status_label = customer_status_label(rec.status)
        title = rec.subject or "(No subject)"
        with st.container(border=True):
            c1, c2 = st.columns([3, 1])
            c1.markdown(f"**{rec.ticket_id}** — {title}")
            c2.markdown(f"**Status:** {status_label}")
            st.write(rec.body)
            if status_label == "Replied" and rec.result and rec.result.draft_reply:
                st.markdown("**Support reply:**")
                st.info(rec.result.draft_reply)


render_customer_page()
